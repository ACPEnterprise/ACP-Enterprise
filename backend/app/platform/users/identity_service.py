import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.auth.services import AuthenticationService
from app.platform.auth.tokens import SecurityTokenService
from app.platform.notifications.repository import (
    NotificationOutboxRepository,
    notification_outbox_repository,
)
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    authorization_service,
)
from app.platform.permissions.codes import AdministrationPermission
from app.platform.users.identity_models import PendingEmailChange
from app.platform.users.identity_repository import (
    IdentityRepositoryConflictError,
    IdentityRepositoryNotFoundError,
    UserIdentityRepository,
    user_identity_repository,
)
from app.platform.users.models import User, UserCredential


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IdentityAdministrationError(Exception):
    pass


class IdentityAdministrationNotFoundError(IdentityAdministrationError):
    pass


class IdentityAdministrationConflictError(IdentityAdministrationError):
    pass


class IdentityAdministrationTokenError(IdentityAdministrationError):
    pass


@dataclass(frozen=True)
class PendingEmailChangeDelivery:
    change: PendingEmailChange
    plaintext_token: str | None
    created: bool


@dataclass(frozen=True)
class IdentityState:
    user_id: UUID
    normalized_email: str
    email_verified_at: datetime | None
    pending_email_change: PendingEmailChange | None
    password_change_required: bool
    password_change_required_at: datetime | None
    password_change_required_reason_code: str | None
    password_change_required_cleared_at: datetime | None
    credential_version: int
    authorization_version: int


class IdentityAdministrationService:
    """Transactional orchestration for identity-administration persistence."""

    def __init__(
        self,
        *,
        repository: UserIdentityRepository = user_identity_repository,
        token_service: SecurityTokenService | None = None,
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        notification_outbox: NotificationOutboxRepository = (
            notification_outbox_repository
        ),
        configuration: Settings = settings,
    ) -> None:
        self.repository = repository
        self.token_service = token_service or SecurityTokenService(configuration)
        self.authorization = authorization
        self.audit = audit
        self.notification_outbox = notification_outbox
        self.configuration = configuration

    async def is_email_available(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_user_id: UUID,
        proposed_email: str,
    ) -> bool:
        self._require_administrator(context)
        normalized_email, _ = self._normalize_email(proposed_email)
        async with session.begin():
            await self._require_company_user(
                session,
                context=context,
                user_id=target_user_id,
            )
            return await self.repository.is_normalized_email_available(
                session,
                normalized_email,
                now=utc_now(),
                excluding_user_id=target_user_id,
            )

    async def request_administrative_email_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_user_id: UUID,
        proposed_email: str,
    ) -> PendingEmailChangeDelivery:
        self._require_administrator(context)
        normalized_email, display_email = self._normalize_email(proposed_email)
        now = utc_now()
        try:
            async with session.begin():
                user = await self._require_company_user(
                    session,
                    context=context,
                    user_id=target_user_id,
                )
                if user.normalized_email == normalized_email:
                    raise IdentityAdministrationConflictError(
                        "Email is already assigned to this identity."
                    )
                plaintext_token = self.token_service.generate_token()
                change = await self.repository.create_pending_email_change(
                    session,
                    user_id=target_user_id,
                    proposed_normalized_email=normalized_email,
                    proposed_display_email=display_email,
                    verification_token_hash=self.token_service.hash_token(
                        plaintext_token
                    ),
                    reason_code="company_administration",
                    initiated_by_user_id=context.user.id,
                    initiating_company_id=context.company.id,
                    expires_at=now
                    + timedelta(
                        seconds=self.configuration.email_verification_lifetime_seconds
                    ),
                    now=now,
                )
                await self.notification_outbox.enqueue(
                    session,
                    notification_type="identity.email_change_verification",
                    template_identifier="identity-email-change-verification-v1",
                    recipient=normalized_email,
                    payload={
                        "change_id": str(change.id),
                        "user_id": str(target_user_id),
                    },
                    correlation_id=change.id,
                    idempotency_key=f"identity.email_change:{change.id}",
                    scheduled_at=now,
                    now=now,
                    company_id=context.company.id,
                    actor_user_id=context.user.id,
                )
                self._stage_events(
                    session,
                    context=context,
                    event_type=EventType.IDENTITY_EMAIL_CHANGE_REQUESTED,
                    audit_action="identity.email_change_requested",
                    resource_id=target_user_id,
                    payload={"change_id": str(change.id)},
                )
            return PendingEmailChangeDelivery(change, plaintext_token, True)
        except IdentityRepositoryNotFoundError as error:
            raise IdentityAdministrationNotFoundError(
                "Identity was not found."
            ) from error
        except IdentityRepositoryConflictError as error:
            raise IdentityAdministrationConflictError(
                "Email is unavailable."
            ) from error

    async def confirm_email_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        plaintext_token: str,
    ) -> User:
        return await self._confirm_email_change(
            session,
            context=context,
            plaintext_token=plaintext_token,
            self_service_only=False,
        )

    async def confirm_own_email_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        plaintext_token: str,
    ) -> User:
        return await self._confirm_email_change(
            session,
            context=context,
            plaintext_token=plaintext_token,
            self_service_only=True,
        )

    async def _confirm_email_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        plaintext_token: str,
        self_service_only: bool,
    ) -> User:
        token_hash = self.token_service.hash_token(plaintext_token)
        now = utc_now()
        try:
            async with session.begin():
                change = await self.repository.get_pending_email_change_for_update(
                    session, token_hash
                )
                if change is None:
                    raise IdentityAdministrationTokenError(
                        "Email-change token is invalid."
                    )
                if self_service_only and change.user_id != context.user.id:
                    raise IdentityAdministrationNotFoundError(
                        "Pending email change was not found."
                    )
                await self._require_actor_can_mutate(
                    session,
                    context=context,
                    target_user_id=change.user_id,
                    initiating_company_id=change.initiating_company_id,
                    enforce_company_origin=True,
                )
                if change.status != "pending" or change.expires_at <= now:
                    raise IdentityAdministrationTokenError(
                        "Email-change token is invalid."
                    )
                self.repository.mark_pending_email_change_confirmed(change, now=now)
                user = await self.repository.apply_verified_email_change(
                    session,
                    user_id=change.user_id,
                    normalized_email=change.proposed_normalized_email,
                    verified_at=now,
                )
                credential = await self.repository.get_credential_for_update(
                    session, change.user_id
                )
                if credential is None:
                    raise IdentityAdministrationNotFoundError(
                        "Identity credential was not found."
                    )
                self.repository.increment_credential_version(credential, updated_at=now)
                await AuthenticationService.revoke_user_sessions(
                    session,
                    user_id=change.user_id,
                    reason="identity_email_changed",
                    now=now,
                )
                self._stage_events(
                    session,
                    context=context,
                    event_type=EventType.IDENTITY_EMAIL_CHANGED,
                    audit_action="identity.email_changed",
                    resource_id=change.user_id,
                    payload={"change_id": str(change.id)},
                )
            return user
        except IdentityRepositoryConflictError as error:
            raise IdentityAdministrationConflictError(
                "Email is unavailable."
            ) from error

    async def revoke_email_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        change_id: UUID,
    ) -> bool:
        self._require_administrator(context)
        now = utc_now()
        async with session.begin():
            change = await self.repository.get_pending_email_change_by_id_for_update(
                session, change_id
            )
            if change is None:
                raise IdentityAdministrationNotFoundError(
                    "Pending email change was not found."
                )
            if change.initiating_company_id != context.company.id:
                raise IdentityAdministrationNotFoundError(
                    "Pending email change was not found."
                )
            await self._require_company_user(
                session,
                context=context,
                user_id=change.user_id,
            )
            if change.status == "revoked":
                return False
            if change.status != "pending":
                raise IdentityAdministrationConflictError(
                    "Pending email change cannot be revoked."
                )
            changed = bool(
                await self.repository.revoke_active_pending_email_changes(
                    session,
                    user_id=change.user_id,
                    now=now,
                )
            )
            if changed:
                self._stage_events(
                    session,
                    context=context,
                    event_type=EventType.IDENTITY_EMAIL_CHANGE_REVOKED,
                    audit_action="identity.email_change_revoked",
                    resource_id=change.user_id,
                    payload={"change_id": str(change.id)},
                )
            return changed

    async def require_password_reset(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_user_id: UUID,
        reason_code: str,
    ) -> tuple[UserCredential, bool]:
        self._require_administrator(context)
        now = utc_now()
        async with session.begin():
            await self._require_company_user(
                session,
                context=context,
                user_id=target_user_id,
            )
            (
                credential,
                changed,
            ) = await self.repository.set_forced_password_reset_required(
                session,
                user_id=target_user_id,
                required_at=now,
                reason_code=reason_code,
                required_by_user_id=context.user.id,
                company_id=context.company.id,
            )
            if changed:
                self.repository.increment_credential_version(credential, updated_at=now)
                await AuthenticationService.revoke_user_sessions(
                    session,
                    user_id=target_user_id,
                    reason="password_change_required",
                    now=now,
                )
                self._stage_events(
                    session,
                    context=context,
                    event_type=EventType.IDENTITY_PASSWORD_RESET_REQUIRED,
                    audit_action="identity.password_reset_required",
                    resource_id=target_user_id,
                    payload={"reason_code": reason_code},
                )
            return credential, changed

    async def clear_password_reset_after_change(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_user_id: UUID,
    ) -> tuple[UserCredential, bool]:
        now = utc_now()
        async with session.begin():
            await self._require_actor_can_mutate(
                session,
                context=context,
                target_user_id=target_user_id,
            )
            (
                credential,
                changed,
            ) = await self.clear_forced_reset_after_verified_password_change(
                session,
                user_id=target_user_id,
                changed_at=now,
            )
            if changed:
                self._stage_events(
                    session,
                    context=context,
                    event_type=EventType.IDENTITY_PASSWORD_RESET_CLEARED,
                    audit_action="identity.password_reset_cleared",
                    resource_id=target_user_id,
                    payload={},
                )
            return credential, changed

    async def clear_forced_reset_after_verified_password_change(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        changed_at: datetime,
    ) -> tuple[UserCredential, bool]:
        """Clear forced-reset state inside the caller-owned password transaction."""
        credential = await self.repository.get_credential_for_update(session, user_id)
        if credential is None:
            raise IdentityAdministrationNotFoundError(
                "Identity credential was not found."
            )
        if not credential.password_change_required:
            return credential, False
        if (
            credential.password_change_required_at is None
            or credential.password_changed_at < credential.password_change_required_at
        ):
            raise IdentityAdministrationConflictError(
                "A successful password change is required."
            )
        return await self.repository.clear_forced_password_reset_required(
            session,
            user_id=user_id,
            cleared_at=changed_at,
        )

    async def expire_pending_email_changes(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_user_id: UUID,
    ) -> int:
        self._require_administrator(context)
        async with session.begin():
            await self._require_company_user(
                session,
                context=context,
                user_id=target_user_id,
            )
            return await self.repository.expire_stale_pending_email_changes(
                session,
                user_id=target_user_id,
                now=utc_now(),
                initiating_company_id=context.company.id,
            )

    async def get_identity_state(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_user_id: UUID,
    ) -> IdentityState:
        await self._require_actor_can_mutate(
            session,
            context=context,
            target_user_id=target_user_id,
        )
        now = utc_now()
        user = await self.repository.get_user_by_id(session, target_user_id)
        credential = await self.repository.get_credential(session, target_user_id)
        if user is None or credential is None:
            raise IdentityAdministrationNotFoundError("Identity was not found.")
        pending = await self.repository.get_active_pending_email_change(
            session,
            user_id=target_user_id,
            now=now,
            initiating_company_id=(
                None if context.user.id == target_user_id else context.company.id
            ),
        )
        return IdentityState(
            user_id=user.id,
            normalized_email=user.normalized_email,
            email_verified_at=user.email_verified_at,
            pending_email_change=pending,
            password_change_required=credential.password_change_required,
            password_change_required_at=credential.password_change_required_at,
            password_change_required_reason_code=(
                credential.password_change_required_reason_code
            ),
            password_change_required_cleared_at=(
                credential.password_change_required_cleared_at
            ),
            credential_version=credential.credential_version,
            authorization_version=user.authorization_version,
        )

    async def _require_company_user(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        user_id: UUID,
    ) -> User:
        user = await self.repository.get_user_by_id(session, user_id)
        if (
            user is None
            or user.status != "active"
            or user.archived_at is not None
            or not await self.repository.has_active_company_membership(
                session,
                user_id=user_id,
                company_id=context.company.id,
            )
        ):
            raise IdentityAdministrationNotFoundError("Identity was not found.")
        return user

    async def _require_actor_can_mutate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target_user_id: UUID,
        initiating_company_id: UUID | None = None,
        enforce_company_origin: bool = False,
    ) -> None:
        if context.user.id == target_user_id:
            return
        self._require_administrator(context)
        if enforce_company_origin and initiating_company_id != context.company.id:
            raise IdentityAdministrationNotFoundError("Identity was not found.")
        await self._require_company_user(
            session,
            context=context,
            user_id=target_user_id,
        )

    def _require_administrator(self, context: AuthorizationContext) -> None:
        self.authorization.require_permission(
            context, AdministrationPermission.COMPANY_ADMINISTER
        )

    @staticmethod
    def _normalize_email(value: str) -> tuple[str, str]:
        display = value.strip()
        normalized = display.lower()
        if len(normalized) > 320 or not re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized
        ):
            raise IdentityAdministrationConflictError("Email is invalid.")
        return normalized, display

    def _stage_events(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        audit_action: str,
        resource_id: UUID,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="user_identity",
                entity_id=resource_id,
                company_id=context.company.id,
                branch_id=(context.active_branch.id if context.active_branch else None),
                user_id=context.user.id,
                payload=payload,
            ),
        )
        self.audit.stage(
            session,
            AuditEntry(
                action=audit_action,
                resource_type="user_identity",
                resource_id=resource_id,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=(context.active_branch.id if context.active_branch else None),
                details=payload,
            ),
        )


identity_administration_service = IdentityAdministrationService()
