from __future__ import annotations

import base64
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.notifications.models import NotificationOutbox
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User

from .models import PasswordResetToken, ProtectedPasswordResetDeliveryEnvelope
from .services import AuthenticationService, normalize_email
from .tokens import SecurityTokenService


class RecoveryDeliveryError(Exception):
    pass


@dataclass(frozen=True)
class RecoveryDelivery:
    token_id: UUID
    outbox_id: UUID
    state: str
    plaintext_token: str | None = None


@dataclass(frozen=True)
class RecoveryDeliveryStatus:
    state: str
    requested_at: datetime | None = None
    expires_at: datetime | None = None
    provider_reference_present: bool = False


@dataclass(frozen=True)
class ProtectedRecoverySecret:
    token_id: UUID
    recipient: str
    display_name: str
    company_name: str
    secret: str
    expires_at: datetime


@dataclass(frozen=True)
class RecoveryScope:
    membership: Membership
    employee: Employee
    branch: Branch
    company: Company


class EmployeeRecoveryDeliveryService:
    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration
        self.tokens = SecurityTokenService(configuration)

    def _keyring(self) -> dict[str, str]:
        if self.configuration.identity_onboarding_delivery_keys:
            return self.configuration.identity_onboarding_delivery_keys
        configured_path = self.configuration.identity_onboarding_delivery_key_file
        if not configured_path:
            return {}
        path = Path(configured_path)
        try:
            metadata = path.stat()
            parent = path.parent.stat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or stat.S_IMODE(parent.st_mode) & 0o077
                or metadata.st_uid != os.geteuid()
            ):
                raise RecoveryDeliveryError("Protected delivery is unavailable.")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in raw.items()
            ):
                raise ValueError("invalid keyring")
            return raw
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise RecoveryDeliveryError("Protected delivery is unavailable.") from error

    def _cipher(self) -> tuple[str, AESGCM]:
        key_id = self.configuration.identity_onboarding_active_delivery_kid
        encoded = self._keyring().get(key_id) if key_id else None
        if not key_id or not encoded:
            raise RecoveryDeliveryError("Protected delivery is unavailable.")
        try:
            return key_id, AESGCM(base64.urlsafe_b64decode(encoded))
        except (TypeError, ValueError) as error:
            raise RecoveryDeliveryError("Protected delivery is unavailable.") from error

    async def request_public(
        self,
        session: AsyncSession,
        *,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RecoveryDelivery | None:
        normalized_email = normalize_email(email)
        async with session.begin():
            user = await session.scalar(
                select(User).where(User.normalized_email == normalized_email)
            )
            AuthenticationService.stage_security_event(
                session,
                event_type="password_reset_requested",
                success=True,
                user_id=user.id if user is not None else None,
                normalized_email=normalized_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            if user is None or user.status != "active" or user.archived_at is not None:
                return None
            scopes = await self._eligible_scopes(session, user_id=user.id)
            if len(scopes) != 1:
                return None
            return await self._issue_locked(
                session,
                user=user,
                scope=scopes[0],
                actor_user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
            )

    async def request_admin(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        user_id: UUID,
    ) -> RecoveryDelivery:
        async with session.begin():
            user = await session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None or user.status != "active" or user.archived_at is not None:
                raise RecoveryDeliveryError("Employee recovery is unavailable.")
            scopes = await self._eligible_scopes(
                session, user_id=user.id, company_id=context.company.id
            )
            if len(scopes) != 1 or not context.can_access_branch(scopes[0].branch.id):
                raise RecoveryDeliveryError("Employee recovery is unavailable.")
            return await self._issue_locked(
                session,
                user=user,
                scope=scopes[0],
                actor_user_id=context.user.id,
                ip_address=None,
                user_agent=None,
            )

    async def status_admin(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        user_id: UUID,
    ) -> RecoveryDeliveryStatus:
        scopes = await self._eligible_scopes(
            session, user_id=user_id, company_id=context.company.id
        )
        if len(scopes) != 1 or not context.can_access_branch(scopes[0].branch.id):
            raise RecoveryDeliveryError("Employee recovery is unavailable.")
        row = (
            await session.execute(
                select(PasswordResetToken, NotificationOutbox)
                .outerjoin(
                    NotificationOutbox,
                    (NotificationOutbox.company_id == context.company.id)
                    & (
                        NotificationOutbox.recipient_reference
                        == ("password-reset:" + PasswordResetToken.id.cast(String))
                    ),
                )
                .where(PasswordResetToken.user_id == user_id)
                .order_by(PasswordResetToken.issued_at.desc())
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return RecoveryDeliveryStatus("RESET_NOT_REQUESTED")
        token, outbox = row
        now = datetime.now(timezone.utc)
        if token.consumed_at is not None:
            state = "RESET_CONSUMED"
        elif token.expires_at <= now or token.revoked_at is not None:
            state = "RESET_EXPIRED"
        elif outbox is None or outbox.status in {
            "pending",
            "claimed",
            "retry_scheduled",
        }:
            state = "RESET_PENDING_DELIVERY"
        elif outbox.status == "accepted":
            state = "RESET_ACCEPTED_BY_PROVIDER"
        elif outbox.status == "sent":
            state = "RESET_DELIVERED"
        elif outbox.status == "ambiguous":
            state = "RESET_UNCERTAIN"
        else:
            state = "RESET_FAILED"
        return RecoveryDeliveryStatus(
            state,
            requested_at=token.issued_at,
            expires_at=token.expires_at,
            provider_reference_present=bool(outbox and outbox.provider_reference),
        )

    async def _eligible_scopes(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        company_id: UUID | None = None,
    ) -> list[RecoveryScope]:
        statement = (
            select(Membership, Employee, Branch, Company)
            .join(
                Employee,
                (Employee.membership_id == Membership.id)
                & (Employee.company_id == Membership.company_id),
            )
            .join(
                Branch,
                (Branch.id == Employee.home_branch_id)
                & (Branch.company_id == Employee.company_id),
            )
            .join(Company, Company.id == Membership.company_id)
            .outerjoin(
                MembershipBranchAccess,
                (MembershipBranchAccess.membership_id == Membership.id)
                & (MembershipBranchAccess.branch_id == Branch.id),
            )
            .where(
                Membership.user_id == user_id,
                Membership.status == "active",
                Employee.status == "active",
                Employee.archived_at.is_(None),
                Branch.status == "active",
                Branch.archived_at.is_(None),
                Company.status == "active",
                Company.archived_at.is_(None),
                (Membership.has_all_branch_access.is_(True))
                | (MembershipBranchAccess.branch_id.is_not(None)),
            )
        )
        if company_id is not None:
            statement = statement.where(Membership.company_id == company_id)
        return [RecoveryScope(*row) for row in (await session.execute(statement)).all()]

    async def _issue_locked(
        self,
        session: AsyncSession,
        *,
        user: User,
        scope: RecoveryScope,
        actor_user_id: UUID | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RecoveryDelivery:
        key_id, cipher = self._cipher()
        now = datetime.now(timezone.utc)
        membership = scope.membership
        employee = scope.employee
        branch = scope.branch
        locked_user = await session.scalar(
            select(User).where(User.id == user.id).with_for_update()
        )
        if (
            locked_user is None
            or locked_user.status != "active"
            or locked_user.archived_at is not None
        ):
            raise RecoveryDeliveryError("Employee recovery is unavailable.")
        current = await session.scalar(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.consumed_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
            )
            .order_by(PasswordResetToken.issued_at.desc())
            .with_for_update()
            .limit(1)
        )
        if current is not None:
            existing_outbox = await session.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.company_id == membership.company_id,
                    NotificationOutbox.recipient_reference
                    == f"password-reset:{current.id}",
                )
            )
            if (
                current.expires_at > now
                and existing_outbox is not None
                and existing_outbox.status
                not in {"failed", "canceled", "suppressed", "ambiguous"}
            ):
                return RecoveryDelivery(
                    current.id, existing_outbox.id, existing_outbox.status
                )
            current.revoked_at = now
            await self._destroy_envelope(session, current.id, now)
        secret = self.tokens.generate_token()
        token = PasswordResetToken(
            user_id=user.id,
            token_hash=self.tokens.hash_token(secret),
            issued_at=now,
            expires_at=now
            + timedelta(seconds=self.configuration.password_reset_lifetime_seconds),
            request_ip_address=ip_address,
            request_user_agent=user_agent,
        )
        session.add(token)
        await session.flush()
        nonce = os.urandom(12)
        session.add(
            ProtectedPasswordResetDeliveryEnvelope(
                password_reset_token_id=token.id,
                company_id=membership.company_id,
                branch_id=branch.id,
                key_id=key_id,
                nonce=nonce,
                ciphertext=cipher.encrypt(
                    nonce, secret.encode(), str(token.id).encode()
                ),
                status="pending",
            )
        )
        outbox, _ = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="identity.password_reset",
            template_identifier="identity-password-reset-v1",
            recipient=user.normalized_email,
            payload={
                "password_reset_token_id": str(token.id),
                "protected_envelope": True,
            },
            correlation_id=uuid4(),
            idempotency_key=f"identity-password-reset:{token.id}",
            scheduled_at=now,
            now=now,
            company_id=membership.company_id,
            branch_id=branch.id,
            channel="email",
            recipient_reference=f"password-reset:{token.id}",
            source_action="identity.password_reset.requested",
            template_version="identity-password-reset-v1",
            actor_user_id=actor_user_id,
        )
        if actor_user_id is not None:
            AuthenticationService.stage_security_event(
                session,
                event_type="password_reset_requested",
                success=True,
                user_id=user.id,
                normalized_email=user.normalized_email,
                ip_address=ip_address,
                user_agent=user_agent,
                occurred_at=now,
            )
            audit_service.stage(
                session,
                AuditEntry(
                    action="identity.password_reset_delivery_requested",
                    resource_type="user",
                    resource_id=user.id,
                    actor_user_id=actor_user_id,
                    company_id=membership.company_id,
                    branch_id=branch.id,
                    details={
                        "employee_id": str(employee.id),
                        "outbox_id": str(outbox.id),
                    },
                ),
            )
        return RecoveryDelivery(
            token.id,
            outbox.id,
            outbox.status,
            secret
            if self.configuration.environment in {"development", "test"}
            else None,
        )

    async def claim(
        self, session: AsyncSession, *, token_id: UUID
    ) -> ProtectedRecoverySecret:
        now = datetime.now(timezone.utc)
        async with session.begin():
            token = await session.scalar(
                select(PasswordResetToken)
                .where(PasswordResetToken.id == token_id)
                .with_for_update()
            )
            envelope = await session.scalar(
                select(ProtectedPasswordResetDeliveryEnvelope)
                .where(
                    ProtectedPasswordResetDeliveryEnvelope.password_reset_token_id
                    == token_id
                )
                .with_for_update()
            )
            unavailable = (
                token is None
                or token.expires_at <= now
                or token.consumed_at is not None
                or token.revoked_at is not None
                or envelope is None
                or envelope.status not in {"pending", "claimed"}
            )
            if unavailable:
                if (
                    token is not None
                    and token.expires_at <= now
                    and token.revoked_at is None
                    and token.consumed_at is None
                ):
                    token.revoked_at = now
                if envelope is not None:
                    envelope.ciphertext = b""
                    envelope.nonce = b""
                    envelope.status = "destroyed"
                    envelope.destroyed_at = now
                result = None
            else:
                assert token is not None and envelope is not None
                scope = await self._eligible_scopes(
                    session, user_id=token.user_id, company_id=envelope.company_id
                )
                if len(scope) != 1 or scope[0].branch.id != envelope.branch_id:
                    raise RecoveryDeliveryError(
                        "Protected recovery delivery is unavailable."
                    )
                user = await session.scalar(
                    select(User).where(User.id == token.user_id)
                )
                if (
                    user is None
                    or user.status != "active"
                    or user.archived_at is not None
                ):
                    raise RecoveryDeliveryError(
                        "Protected recovery delivery is unavailable."
                    )
                encoded = self._keyring().get(envelope.key_id)
                if not encoded:
                    raise RecoveryDeliveryError(
                        "Protected recovery delivery is unavailable."
                    )
                try:
                    secret = (
                        AESGCM(base64.urlsafe_b64decode(encoded))
                        .decrypt(
                            envelope.nonce,
                            envelope.ciphertext,
                            str(token.id).encode(),
                        )
                        .decode()
                    )
                except (TypeError, ValueError) as error:
                    raise RecoveryDeliveryError(
                        "Protected recovery delivery is unavailable."
                    ) from error
                envelope.status = "claimed"
                result = ProtectedRecoverySecret(
                    token.id,
                    user.normalized_email,
                    user.display_name,
                    scope[0].company.name,
                    secret,
                    token.expires_at,
                )
        if result is None:
            raise RecoveryDeliveryError("Protected recovery delivery is unavailable.")
        return result

    async def complete(self, session: AsyncSession, *, token_id: UUID) -> None:
        async with session.begin():
            await self._destroy_envelope(
                session, token_id, datetime.now(timezone.utc), delivered=True
            )

    @staticmethod
    async def _destroy_envelope(
        session: AsyncSession,
        token_id: UUID,
        now: datetime,
        *,
        delivered: bool = False,
    ) -> None:
        envelope = await session.scalar(
            select(ProtectedPasswordResetDeliveryEnvelope)
            .where(
                ProtectedPasswordResetDeliveryEnvelope.password_reset_token_id
                == token_id
            )
            .with_for_update()
        )
        if envelope is not None:
            envelope.ciphertext = b""
            envelope.nonce = b""
            envelope.status = "delivered" if delivered else "destroyed"
            envelope.destroyed_at = now


employee_recovery_delivery_service = EmployeeRecoveryDeliveryService()
