from datetime import datetime, timedelta, timezone
import re
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    PermissionDeniedError,
    authorization_service,
)
from app.platform.permissions.codes import WorkerIdentityPermission
from app.worker_identity.contracts import (
    WorkerCredentialIssuer,
    WorkerCredentialState,
    WorkerIdentityState,
)
from app.worker_identity.errors import (
    WorkerIdentityConflictError,
    WorkerIdentityLifecycleError,
    WorkerIdentityNotFoundError,
    WorkerIdentityPermissionError,
    WorkerIdentityValidationError,
)
from app.worker_identity.records import WorkerCredentialRecord, WorkerIdentityRecord
from app.worker_identity.repository import WorkerIdentityRepository

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,99}$")
MIN_CREDENTIAL_LIFETIME = timedelta(minutes=5)
MAX_CREDENTIAL_LIFETIME = timedelta(days=90)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerIdentityService:
    def __init__(
        self,
        *,
        issuer: WorkerCredentialIssuer,
        repository: WorkerIdentityRepository | None = None,
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
    ) -> None:
        self.issuer = issuer
        self.repository = repository or WorkerIdentityRepository()
        self.authorization = authorization
        self.audit = audit

    async def register(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        name: str,
        now: datetime | None = None,
    ) -> WorkerIdentityRecord:
        self._require(context)
        normalized = name.strip()
        if not SAFE_NAME.fullmatch(normalized):
            raise WorkerIdentityValidationError("Worker identity name is invalid.")
        occurred_at = now or utc_now()
        try:
            async with session.begin():
                record = await self.repository.create_identity(
                    session,
                    company_id=context.company.id,
                    name=normalized,
                    registered_by_user_id=context.user.id,
                    now=occurred_at,
                )
                self._evidence(
                    session,
                    context=context,
                    record=record,
                    action="engineering.worker_identity_registered",
                    event_type=EventType.WORKER_IDENTITY_REGISTERED,
                    occurred_at=occurred_at,
                )
            return record
        except IntegrityError as error:
            await session.rollback()
            raise WorkerIdentityConflictError(
                "Worker identity already exists."
            ) from error

    async def transition_identity(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        identity_id: UUID,
        expected_version: int,
        state: WorkerIdentityState,
        now: datetime | None = None,
    ) -> WorkerIdentityRecord:
        self._require(context)
        if state not in {
            WorkerIdentityState.ACTIVE,
            WorkerIdentityState.SUSPENDED,
            WorkerIdentityState.REVOKED,
        }:
            raise WorkerIdentityLifecycleError("Identity transition is unsupported.")
        occurred_at = now or utc_now()
        async with session.begin():
            identity = await self.repository.get_identity_for_update(
                session, company_id=context.company.id, identity_id=identity_id
            )
            if identity is None:
                raise WorkerIdentityNotFoundError("Worker identity was not found.")
            if identity.version != expected_version:
                raise WorkerIdentityConflictError("Worker identity version is stale.")
            current = WorkerIdentityState(identity.state)
            if current is state:
                return self.repository.snapshot_identity(identity)
            allowed = {
                WorkerIdentityState.REGISTERED: {WorkerIdentityState.ACTIVE},
                WorkerIdentityState.ACTIVE: {
                    WorkerIdentityState.SUSPENDED,
                    WorkerIdentityState.REVOKED,
                },
                WorkerIdentityState.SUSPENDED: {
                    WorkerIdentityState.ACTIVE,
                    WorkerIdentityState.REVOKED,
                },
                WorkerIdentityState.REVOKED: set(),
            }
            if state not in allowed[current]:
                raise WorkerIdentityLifecycleError("Identity transition is invalid.")
            record = await self.repository.set_identity_state(
                session, identity=identity, state=state, now=occurred_at
            )
            self._evidence(
                session,
                context=context,
                record=record,
                action=f"engineering.worker_identity_{state.value}",
                event_type=EventType.WORKER_IDENTITY_STATE_CHANGED,
                occurred_at=occurred_at,
            )
            return record

    async def issue_credential(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        identity_id: UUID,
        lifetime: timedelta,
        now: datetime | None = None,
    ) -> WorkerCredentialRecord:
        self._require(context)
        if lifetime < MIN_CREDENTIAL_LIFETIME or lifetime > MAX_CREDENTIAL_LIFETIME:
            raise WorkerIdentityValidationError("Credential lifetime is invalid.")
        occurred_at = now or utc_now()
        async with session.begin():
            identity = await self.repository.get_identity_for_update(
                session, company_id=context.company.id, identity_id=identity_id
            )
            if identity is None:
                raise WorkerIdentityNotFoundError("Worker identity was not found.")
            if identity.state == WorkerIdentityState.REVOKED.value:
                raise WorkerIdentityLifecycleError(
                    "Revoked identity cannot issue credentials."
                )
            current = await self.repository.get_active_credential_for_update(
                session, company_id=context.company.id, identity_id=identity_id
            )
            next_version = 1 if current is None else current.version + 1
            metadata = await self.issuer.issue(
                identity_id=identity.id, credential_version=next_version
            )
            self._validate_metadata(
                metadata.verifier, metadata.verifier_algorithm, metadata.public_key_id
            )
            record = await self.repository.issue_credential(
                session,
                identity=identity,
                metadata=metadata,
                expires_at=occurred_at + lifetime,
                now=occurred_at,
            )
            self._credential_evidence(
                session,
                context=context,
                record=record,
                action="engineering.worker_credential_issued",
                event_type=EventType.WORKER_CREDENTIAL_ISSUED,
                occurred_at=occurred_at,
            )
            return record

    async def activate_credential(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        credential_id: UUID,
        now: datetime | None = None,
    ) -> WorkerCredentialRecord:
        return await self._credential_transition(
            session,
            context=context,
            credential_id=credential_id,
            state=WorkerCredentialState.ACTIVE,
            now=now,
        )

    async def revoke_credential(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        credential_id: UUID,
        now: datetime | None = None,
    ) -> WorkerCredentialRecord:
        return await self._credential_transition(
            session,
            context=context,
            credential_id=credential_id,
            state=WorkerCredentialState.REVOKED,
            now=now,
        )

    async def expire_credential(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        credential_id: UUID,
        now: datetime | None = None,
    ) -> WorkerCredentialRecord:
        return await self._credential_transition(
            session,
            context=context,
            credential_id=credential_id,
            state=WorkerCredentialState.EXPIRED,
            now=now,
        )

    async def _credential_transition(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        credential_id: UUID,
        state: WorkerCredentialState,
        now: datetime | None,
    ) -> WorkerCredentialRecord:
        self._require(context)
        occurred_at = now or utc_now()
        async with session.begin():
            credential = await self.repository.get_credential_for_update(
                session, company_id=context.company.id, credential_id=credential_id
            )
            if credential is None:
                raise WorkerIdentityNotFoundError("Worker credential was not found.")
            current = WorkerCredentialState(credential.state)
            if current is state:
                return self.repository.snapshot_credential(credential)
            if current in {
                WorkerCredentialState.REVOKED,
                WorkerCredentialState.EXPIRED,
            }:
                raise WorkerIdentityLifecycleError("Credential is terminal.")
            if state is WorkerCredentialState.ACTIVE:
                if (
                    current is not WorkerCredentialState.PENDING
                    or credential.expires_at <= occurred_at
                ):
                    raise WorkerIdentityLifecycleError(
                        "Credential cannot be activated."
                    )
                active = await self.repository.get_active_credential_for_update(
                    session,
                    company_id=context.company.id,
                    identity_id=credential.identity_id,
                )
                if active is not None and active.id != credential.id:
                    await self.repository.transition_credential(
                        session,
                        credential=active,
                        state=WorkerCredentialState.REVOKED,
                        now=occurred_at,
                    )
            elif (
                state is WorkerCredentialState.EXPIRED
                and credential.expires_at > occurred_at
            ):
                raise WorkerIdentityLifecycleError("Credential has not expired.")
            record = await self.repository.transition_credential(
                session, credential=credential, state=state, now=occurred_at
            )
            event = {
                WorkerCredentialState.ACTIVE: EventType.WORKER_CREDENTIAL_ACTIVATED,
                WorkerCredentialState.REVOKED: EventType.WORKER_CREDENTIAL_REVOKED,
                WorkerCredentialState.EXPIRED: EventType.WORKER_CREDENTIAL_EXPIRED,
            }[state]
            self._credential_evidence(
                session,
                context=context,
                record=record,
                action=f"engineering.worker_credential_{state.value}",
                event_type=event,
                occurred_at=occurred_at,
            )
            return record

    def _require(self, context: AuthorizationContext) -> None:
        if context.membership.status != "active":
            raise WorkerIdentityPermissionError("Permission denied.")
        try:
            self.authorization.require_permission(
                context, WorkerIdentityPermission.MANAGE
            )
        except PermissionDeniedError as error:
            raise WorkerIdentityPermissionError("Permission denied.") from error

    @staticmethod
    def _validate_metadata(verifier: str, algorithm: str, key_id: str) -> None:
        if not verifier.strip() or not algorithm.strip() or not key_id.strip():
            raise WorkerIdentityValidationError("Credential metadata is invalid.")
        lowered = algorithm.lower()
        if lowered not in {"ed25519", "p256", "rsa-pss-sha256"}:
            raise WorkerIdentityValidationError("Verifier algorithm is unsupported.")

    def _evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        record: WorkerIdentityRecord,
        action: str,
        event_type: EventType,
        occurred_at: datetime,
    ) -> None:
        details: dict[str, object] = {
            "identity_id": str(record.id),
            "state": record.state.value,
            "version": record.version,
        }
        self._stage(
            session,
            context=context,
            resource_id=record.id,
            action=action,
            event_type=event_type,
            details=details,
            occurred_at=occurred_at,
        )

    def _credential_evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        record: WorkerCredentialRecord,
        action: str,
        event_type: EventType,
        occurred_at: datetime,
    ) -> None:
        details: dict[str, object] = {
            "identity_id": str(record.identity_id),
            "record_id": str(record.id),
            "state": record.state.value,
            "version": record.version,
            "public_key_id": record.public_key_id,
        }
        self._stage(
            session,
            context=context,
            resource_id=record.id,
            action=action,
            event_type=event_type,
            details=details,
            occurred_at=occurred_at,
        )

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        resource_id: UUID,
        action: str,
        event_type: EventType,
        details: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        correlation_id = uuid4()
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="worker_identity",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=resource_id,
                correlation_id=correlation_id,
                details=details,
                occurred_at=occurred_at,
            ),
        )
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="worker_identity",
                entity_id=resource_id,
                company_id=context.company.id,
                user_id=context.user.id,
                correlation_id=correlation_id,
                payload=details,
                occurred_at=occurred_at,
            ),
        )
