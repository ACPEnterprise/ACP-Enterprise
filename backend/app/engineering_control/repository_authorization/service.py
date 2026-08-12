import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.review.contracts import (
    EngineeringReviewDecision,
    EngineeringReviewState,
)
from app.engineering_control.review.repository import EngineeringReviewSource
from app.engineering_control.review.service import calculate_review_digest
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
from app.platform.permissions.codes import EngineeringCommandPermission

from .contracts import (
    RepositoryAuthorizationEventType,
    RepositoryAuthorizationState,
    RepositoryOperationType,
)
from .errors import (
    RepositoryAuthorizationConflictError,
    RepositoryAuthorizationEvidenceMismatchError,
    RepositoryAuthorizationIneligibleError,
    RepositoryAuthorizationNotFoundError,
)
from .records import (
    RepositoryAuthorizationEligibility,
    RepositoryAuthorizationRecord,
    RequestRepositoryAuthorization,
    RevokeRepositoryAuthorization,
    ValidateRepositoryAuthorization,
)
from .repository import (
    EngineeringRepositoryAuthorizationRepository,
    RepositoryAuthorizationSource,
)

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
MAX_AUTHORIZATION_LIFETIME = timedelta(hours=1)
MAX_FILE_BOUNDARY = 200


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringRepositoryAuthorizationService:
    def __init__(
        self,
        *,
        repository: type[EngineeringRepositoryAuthorizationRepository] = (
            EngineeringRepositoryAuthorizationRepository
        ),
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.authorization = authorization
        self.audit = audit
        self.events = events

    async def request(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RequestRepositoryAuthorization,
        now: datetime | None = None,
    ) -> RepositoryAuthorizationRecord:
        self._require(context, EngineeringCommandPermission.APPROVE)
        occurred_at = now or utc_now()
        boundary = self._file_boundary(command.file_boundary)
        self._validate_request(command, now=occurred_at)
        try:
            async with session.begin():
                source = await self._source(
                    session,
                    context=context,
                    review_id=command.review_id,
                )
                self._validate_evidence(
                    source,
                    review_digest=command.review_digest,
                    operation_type=command.operation_type,
                    file_boundary=boundary,
                    expected_branch=command.expected_branch,
                    expected_base_commit=command.expected_base_commit,
                )
                existing = await self.repository.get_by_idempotency(
                    session,
                    company_id=context.company.id,
                    idempotency_key=command.idempotency_key,
                )
                if existing is not None:
                    expected = self._authorization_digest(
                        source=source,
                        capability_id=existing.capability_id,
                        operation_type=command.operation_type,
                        file_boundary=boundary,
                        expected_branch=command.expected_branch,
                        expected_base_commit=command.expected_base_commit,
                        expires_at=command.expires_at,
                    )
                    if existing.authorization_digest != expected:
                        raise RepositoryAuthorizationConflictError(
                            "Authorization idempotency key conflicts."
                        )
                    return existing
                capability_id = uuid4()
                digest = self._authorization_digest(
                    source=source,
                    capability_id=capability_id,
                    operation_type=command.operation_type,
                    file_boundary=boundary,
                    expected_branch=command.expected_branch,
                    expected_base_commit=command.expected_base_commit,
                    expires_at=command.expires_at,
                )
                record = await self.repository.create(
                    session,
                    source=source,
                    authorized_by_user_id=context.user.id,
                    capability_id=capability_id,
                    operation_type=command.operation_type,
                    file_boundary=boundary,
                    expected_branch=command.expected_branch,
                    expected_base_commit=command.expected_base_commit,
                    review_digest=command.review_digest,
                    authorization_digest=digest,
                    idempotency_key=command.idempotency_key,
                    authorized_at=occurred_at,
                    expires_at=command.expires_at,
                )
                await self.repository.append_event(
                    session,
                    authorization=record,
                    actor_user_id=context.user.id,
                    event_type=RepositoryAuthorizationEventType.REQUESTED,
                    reason_code=None,
                    now=occurred_at,
                )
                await self.repository.append_event(
                    session,
                    authorization=record,
                    actor_user_id=context.user.id,
                    event_type=RepositoryAuthorizationEventType.GRANTED,
                    reason_code=None,
                    now=occurred_at,
                )
                self._stage(
                    session,
                    context=context,
                    record=record,
                    event_type=EventType.ENGINEERING_REPOSITORY_AUTHORIZATION_REQUESTED,
                    action="engineering.repository_authorization_requested",
                    reason_code=None,
                    now=occurred_at,
                )
                self._stage(
                    session,
                    context=context,
                    record=record,
                    event_type=EventType.ENGINEERING_REPOSITORY_AUTHORIZATION_GRANTED,
                    action="engineering.repository_authorization_granted",
                    reason_code=None,
                    now=occurred_at,
                )
                return record
        except IntegrityError as error:
            await session.rollback()
            raise RepositoryAuthorizationConflictError(
                "Repository authorization conflicted."
            ) from error

    async def get(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        authorization_id: UUID,
        now: datetime | None = None,
    ) -> RepositoryAuthorizationRecord:
        self._require(context, EngineeringCommandPermission.READ)
        occurred_at = now or utc_now()
        async with session.begin():
            record = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                authorization_id=authorization_id,
            )
            if record is None:
                raise RepositoryAuthorizationNotFoundError(
                    "Repository authorization not found."
                )
            return await self._expire_if_needed(
                session,
                context=context,
                record=record,
                now=occurred_at,
            )

    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        state: RepositoryAuthorizationState | None = None,
        limit: int = 50,
    ) -> tuple[RepositoryAuthorizationRecord, ...]:
        self._require(context, EngineeringCommandPermission.READ)
        if not 1 <= limit <= 100:
            raise RepositoryAuthorizationIneligibleError(
                "Authorization limit is invalid."
            )
        return await self.repository.list(
            session,
            company_id=context.company.id,
            state=state,
            limit=limit,
        )

    async def eligibility(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ValidateRepositoryAuthorization,
        now: datetime | None = None,
    ) -> RepositoryAuthorizationEligibility:
        try:
            await self.validate(
                session,
                context=context,
                command=command,
                now=now,
            )
        except (
            RepositoryAuthorizationIneligibleError,
            RepositoryAuthorizationEvidenceMismatchError,
            RepositoryAuthorizationNotFoundError,
        ) as error:
            return RepositoryAuthorizationEligibility(
                False,
                type(error).__name__,
                UUID(int=0),
                command.operation_type,
            )
        record = await self.get(
            session,
            context=context,
            authorization_id=command.authorization_id,
            now=now,
        )
        return RepositoryAuthorizationEligibility(
            True,
            None,
            record.review_id,
            record.operation_type,
        )

    async def validate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ValidateRepositoryAuthorization,
        now: datetime | None = None,
    ) -> RepositoryAuthorizationRecord:
        self._require(context, EngineeringCommandPermission.APPROVE)
        occurred_at = now or utc_now()
        boundary = self._file_boundary(command.file_boundary)
        expired = False
        async with session.begin():
            record = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                authorization_id=command.authorization_id,
            )
            if record is None:
                raise RepositoryAuthorizationNotFoundError(
                    "Repository authorization not found."
                )
            record = await self._expire_if_needed(
                session,
                context=context,
                record=record,
                now=occurred_at,
            )
            if record.state is RepositoryAuthorizationState.EXPIRED:
                expired = True
            else:
                self._validate_capability(record, command, boundary)
                return record
        if expired:
            raise RepositoryAuthorizationIneligibleError(
                "Repository authorization is expired."
            )
        raise RepositoryAuthorizationIneligibleError(
            "Repository authorization is not active."
        )

    async def validate_in_transaction(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ValidateRepositoryAuthorization,
        now: datetime,
    ) -> RepositoryAuthorizationRecord:
        """Validate exact current evidence inside a caller-owned transaction."""
        self._require(context, EngineeringCommandPermission.APPROVE)
        boundary = self._file_boundary(command.file_boundary)
        record = await self.repository.get_for_update(
            session,
            company_id=context.company.id,
            authorization_id=command.authorization_id,
        )
        if record is None:
            raise RepositoryAuthorizationNotFoundError(
                "Repository authorization not found."
            )
        if record.expires_at <= now:
            raise RepositoryAuthorizationIneligibleError(
                "Repository authorization is expired."
            )
        self._validate_capability(record, command, boundary)
        source = await self._source(
            session,
            context=context,
            review_id=record.review_id,
        )
        self._validate_evidence(
            source,
            review_digest=record.review_digest,
            operation_type=record.operation_type,
            file_boundary=record.file_boundary,
            expected_branch=record.expected_branch,
            expected_base_commit=record.expected_base_commit,
        )
        return record

    async def consume_in_transaction(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ValidateRepositoryAuthorization,
        now: datetime,
    ) -> RepositoryAuthorizationRecord:
        """Consume exact authorization inside a caller-owned transaction."""
        record = await self.validate_in_transaction(
            session,
            context=context,
            command=command,
            now=now,
        )
        consumed = await self.repository.transition(
            session,
            company_id=context.company.id,
            authorization_id=record.id,
            expected_version=record.version,
            target=RepositoryAuthorizationState.CONSUMED,
            now=now,
        )
        if consumed is None:
            raise RepositoryAuthorizationConflictError("Authorization version changed.")
        await self.repository.append_event(
            session,
            authorization=consumed,
            actor_user_id=context.user.id,
            event_type=RepositoryAuthorizationEventType.CONSUMED,
            reason_code=None,
            now=now,
        )
        self._stage(
            session,
            context=context,
            record=consumed,
            event_type=EventType.ENGINEERING_REPOSITORY_AUTHORIZATION_CONSUMED,
            action="engineering.repository_authorization_consumed",
            reason_code=None,
            now=now,
        )
        return consumed

    async def consume(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ValidateRepositoryAuthorization,
        now: datetime | None = None,
    ) -> RepositoryAuthorizationRecord:
        self._require(context, EngineeringCommandPermission.APPROVE)
        occurred_at = now or utc_now()
        boundary = self._file_boundary(command.file_boundary)
        expired = False
        consumed: RepositoryAuthorizationRecord | None = None
        async with session.begin():
            record = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                authorization_id=command.authorization_id,
            )
            if record is None:
                raise RepositoryAuthorizationNotFoundError(
                    "Repository authorization not found."
                )
            record = await self._expire_if_needed(
                session,
                context=context,
                record=record,
                now=occurred_at,
            )
            if record.state is RepositoryAuthorizationState.EXPIRED:
                expired = True
            else:
                self._validate_capability(record, command, boundary)
                consumed = await self.repository.transition(
                    session,
                    company_id=context.company.id,
                    authorization_id=record.id,
                    expected_version=record.version,
                    target=RepositoryAuthorizationState.CONSUMED,
                    now=occurred_at,
                )
                if consumed is None:
                    raise RepositoryAuthorizationConflictError(
                        "Authorization version changed."
                    )
                await self.repository.append_event(
                    session,
                    authorization=consumed,
                    actor_user_id=context.user.id,
                    event_type=RepositoryAuthorizationEventType.CONSUMED,
                    reason_code=None,
                    now=occurred_at,
                )
                self._stage(
                    session,
                    context=context,
                    record=consumed,
                    event_type=EventType.ENGINEERING_REPOSITORY_AUTHORIZATION_CONSUMED,
                    action="engineering.repository_authorization_consumed",
                    reason_code=None,
                    now=occurred_at,
                )
        if expired:
            raise RepositoryAuthorizationIneligibleError(
                "Repository authorization is expired."
            )
        if consumed is None:
            raise RepositoryAuthorizationIneligibleError(
                "Repository authorization is not active."
            )
        return consumed

    async def revoke(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RevokeRepositoryAuthorization,
        now: datetime | None = None,
    ) -> RepositoryAuthorizationRecord:
        self._require(context, EngineeringCommandPermission.APPROVE)
        if REASON_CODE.fullmatch(command.reason_code) is None:
            raise RepositoryAuthorizationIneligibleError(
                "Revocation reason is invalid."
            )
        occurred_at = now or utc_now()
        async with session.begin():
            record = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                authorization_id=command.authorization_id,
            )
            if record is None:
                raise RepositoryAuthorizationNotFoundError(
                    "Repository authorization not found."
                )
            if record.version != command.expected_version:
                raise RepositoryAuthorizationConflictError(
                    "Authorization version changed."
                )
            if record.state is RepositoryAuthorizationState.REVOKED:
                return record
            if record.state is not RepositoryAuthorizationState.AUTHORIZED:
                raise RepositoryAuthorizationIneligibleError(
                    "Authorization cannot be revoked."
                )
            revoked = await self.repository.transition(
                session,
                company_id=context.company.id,
                authorization_id=record.id,
                expected_version=record.version,
                target=RepositoryAuthorizationState.REVOKED,
                now=occurred_at,
            )
            if revoked is None:
                raise RepositoryAuthorizationConflictError(
                    "Authorization version changed."
                )
            await self.repository.append_event(
                session,
                authorization=revoked,
                actor_user_id=context.user.id,
                event_type=RepositoryAuthorizationEventType.REVOKED,
                reason_code=command.reason_code,
                now=occurred_at,
            )
            self._stage(
                session,
                context=context,
                record=revoked,
                event_type=EventType.ENGINEERING_REPOSITORY_AUTHORIZATION_REVOKED,
                action="engineering.repository_authorization_revoked",
                reason_code=command.reason_code,
                now=occurred_at,
            )
            return revoked

    async def _source(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        review_id: UUID,
    ) -> RepositoryAuthorizationSource:
        source = await self.repository.load_source_for_update(
            session,
            company_id=context.company.id,
            review_id=review_id,
        )
        if source is None:
            raise RepositoryAuthorizationNotFoundError(
                "Accepted Engineering review not found."
            )
        return source

    @staticmethod
    def _validate_request(
        command: RequestRepositoryAuthorization,
        *,
        now: datetime,
    ) -> None:
        if (
            command.expires_at <= now
            or command.expires_at > now + MAX_AUTHORIZATION_LIFETIME
        ):
            raise RepositoryAuthorizationIneligibleError(
                "Authorization expiration is invalid."
            )
        if IDEMPOTENCY_KEY.fullmatch(command.idempotency_key) is None:
            raise RepositoryAuthorizationIneligibleError(
                "Authorization idempotency key is invalid."
            )
        if FULL_SHA.fullmatch(command.expected_base_commit) is None:
            raise RepositoryAuthorizationIneligibleError(
                "Expected base commit is invalid."
            )

    @staticmethod
    def _validate_evidence(
        source: RepositoryAuthorizationSource,
        *,
        review_digest: str,
        operation_type: RepositoryOperationType,
        file_boundary: tuple[str, ...],
        expected_branch: str,
        expected_base_commit: str,
    ) -> None:
        review_source = EngineeringReviewSource(
            source.command,
            source.execution,
            source.composition,
            source.attempt,
            source.result,
        )
        authoritative_digest = calculate_review_digest(review_source)
        if (
            source.review.state != EngineeringReviewState.ACCEPTED.value
            or source.decision.decision != EngineeringReviewDecision.ACCEPT.value
            or source.review.review_digest != review_digest
            or source.decision.review_digest != review_digest
            or authoritative_digest != review_digest
        ):
            raise RepositoryAuthorizationEvidenceMismatchError(
                "Accepted review evidence is stale or mismatched."
            )
        if (
            source.result.status != "succeeded"
            or source.result.disposition != "accepted"
            or source.result.repository_mutated
            or not source.command.requested_code_changes
        ):
            raise RepositoryAuthorizationIneligibleError(
                "Execution result is not eligible for repository authorization."
            )
        if (
            operation_type is not RepositoryOperationType.CREATE_COMMIT
            or expected_branch != source.command.expected_branch
            or expected_branch != source.composition.expected_branch
            or expected_base_commit != source.command.expected_head
            or expected_base_commit != source.composition.expected_head
        ):
            raise RepositoryAuthorizationEvidenceMismatchError(
                "Repository operation scope does not match approved evidence."
            )
        evidence_boundary = source.result.validation_summary.get("file_boundary")
        if (
            not isinstance(evidence_boundary, list)
            or tuple(sorted(evidence_boundary)) != file_boundary
        ):
            raise RepositoryAuthorizationEvidenceMismatchError(
                "File boundary does not match reviewed evidence."
            )

    @staticmethod
    def _authorization_digest(
        *,
        source: RepositoryAuthorizationSource,
        capability_id: UUID,
        operation_type: RepositoryOperationType,
        file_boundary: tuple[str, ...],
        expected_branch: str,
        expected_base_commit: str,
        expires_at: datetime,
    ) -> str:
        payload = {
            "capability_id": str(capability_id),
            "company_id": str(source.review.company_id),
            "command_id": str(source.review.command_id),
            "execution_id": str(source.review.execution_id),
            "result_id": str(source.review.result_id),
            "review_id": str(source.review.id),
            "review_decision_id": str(source.decision.id),
            "review_digest": source.review.review_digest,
            "operation_type": operation_type.value,
            "file_boundary": file_boundary,
            "expected_branch": expected_branch,
            "expected_base_commit": expected_base_commit,
            "expires_at": expires_at.isoformat(),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _file_boundary(file_boundary: tuple[str, ...]) -> tuple[str, ...]:
        if not file_boundary or len(file_boundary) > MAX_FILE_BOUNDARY:
            raise RepositoryAuthorizationIneligibleError("File boundary is invalid.")
        normalized: list[str] = []
        for value in file_boundary:
            path = PurePosixPath(value)
            if (
                not value
                or len(value) > 500
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in value
                or value.endswith("/")
            ):
                raise RepositoryAuthorizationIneligibleError(
                    "File boundary is invalid."
                )
            normalized.append(path.as_posix())
        if len(set(normalized)) != len(normalized):
            raise RepositoryAuthorizationIneligibleError(
                "File boundary contains duplicates."
            )
        return tuple(sorted(normalized))

    @staticmethod
    def _validate_capability(
        record: RepositoryAuthorizationRecord,
        command: ValidateRepositoryAuthorization,
        boundary: tuple[str, ...],
    ) -> None:
        if record.state is not RepositoryAuthorizationState.AUTHORIZED:
            raise RepositoryAuthorizationIneligibleError(
                "Repository authorization is not active."
            )
        if (
            record.capability_id != command.capability_id
            or record.authorization_digest != command.authorization_digest
            or record.operation_type is not command.operation_type
            or record.file_boundary != boundary
            or record.expected_branch != command.expected_branch
            or record.expected_base_commit != command.expected_base_commit
        ):
            raise RepositoryAuthorizationEvidenceMismatchError(
                "Repository authorization capability does not match."
            )

    async def _expire_if_needed(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        record: RepositoryAuthorizationRecord,
        now: datetime,
    ) -> RepositoryAuthorizationRecord:
        if (
            record.state is RepositoryAuthorizationState.AUTHORIZED
            and record.expires_at <= now
        ):
            expired = await self.repository.transition(
                session,
                company_id=context.company.id,
                authorization_id=record.id,
                expected_version=record.version,
                target=RepositoryAuthorizationState.EXPIRED,
                now=now,
            )
            if expired is None:
                raise RepositoryAuthorizationConflictError(
                    "Authorization version changed."
                )
            await self.repository.append_event(
                session,
                authorization=expired,
                actor_user_id=context.user.id,
                event_type=RepositoryAuthorizationEventType.EXPIRED,
                reason_code="authorization_expired",
                now=now,
            )
            self._stage(
                session,
                context=context,
                record=expired,
                event_type=EventType.ENGINEERING_REPOSITORY_AUTHORIZATION_EXPIRED,
                action="engineering.repository_authorization_expired",
                reason_code="authorization_expired",
                now=now,
            )
            return expired
        return record

    def _require(self, context: AuthorizationContext, permission: str) -> None:
        try:
            self.authorization.require_permission(context, permission)
        except PermissionDeniedError as error:
            raise RepositoryAuthorizationNotFoundError(
                "Repository authorization not found."
            ) from error

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        record: RepositoryAuthorizationRecord,
        event_type: EventType,
        action: str,
        reason_code: str | None,
        now: datetime,
    ) -> None:
        evidence: dict[str, object] = {
            "authorization_id": str(record.id),
            "capability_id": str(record.capability_id),
            "command_id": str(record.command_id),
            "execution_id": str(record.execution_id),
            "review_id": str(record.review_id),
            "operation_type": record.operation_type.value,
            "state": record.state.value,
            "version": record.version,
            "reason_code": reason_code,
            "expires_at": record.expires_at.isoformat(),
        }
        audit_evidence = {**evidence, "record_id": evidence["authorization_id"]}
        del audit_evidence["authorization_id"]
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_repository_authorization",
                company_id=context.company.id,
                resource_id=record.id,
                details=audit_evidence,
                occurred_at=now,
            ),
        )
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_repository_authorization",
                entity_id=record.id,
                company_id=context.company.id,
                payload=evidence,
                occurred_at=now,
            ),
        )


engineering_repository_authorization_service = (
    EngineeringRepositoryAuthorizationService()
)
