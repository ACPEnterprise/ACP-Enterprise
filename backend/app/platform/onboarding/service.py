import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.services import credential_service, normalize_email
from app.platform.auth.tokens import SecurityTokenService
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.employees.models import Employee
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User, UserCredential

from .models import (
    EmployeeNumberPolicy,
    IdentityOnboardingInvitation,
    IdentityOnboardingRequest,
    ProtectedInvitationDeliveryEnvelope,
)


class OnboardingError(Exception):
    pass


class OnboardingConflictError(OnboardingError):
    pass


class OnboardingAuthorizationError(OnboardingError):
    pass


@dataclass(frozen=True)
class OnboardingCommand:
    request_key: str
    branch_id: UUID
    first_name: str
    last_name: str
    display_name: str
    employee_type: str
    employee_number_prefix: str
    employee_number_width: int
    role_ids: tuple[UUID, ...] = ()
    login_email: str | None = None
    existing_user_id: UUID | None = None


@dataclass(frozen=True)
class ProtectedInvitationDelivery:
    invitation_id: UUID
    recipient: str
    secret: str


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _masked(email: str) -> str:
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


class IdentityOnboardingService:
    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration
        self.tokens = SecurityTokenService(configuration)

    def _require_admin(self, context: AuthorizationContext) -> None:
        if not context.has_permission(
            AdministrationPermission.IDENTITY_ONBOARDING_MANAGE
        ):
            raise OnboardingAuthorizationError("Onboarding authority is required.")

    def _delivery_cipher(self) -> tuple[str, AESGCM]:
        key_id = self.configuration.identity_onboarding_active_delivery_kid
        encoded = (
            self.configuration.identity_onboarding_delivery_keys.get(key_id)
            if key_id
            else None
        )
        if not key_id or not encoded:
            raise OnboardingConflictError(
                "Protected invitation delivery is not configured."
            )
        try:
            key = base64.urlsafe_b64decode(encoded)
            return key_id, AESGCM(key)
        except (ValueError, TypeError) as error:
            raise OnboardingConflictError(
                "Protected invitation delivery is not configured."
            ) from error

    async def initiate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: OnboardingCommand,
    ) -> IdentityOnboardingRequest:
        self._require_admin(context)
        key_id, cipher = self._delivery_cipher()
        request_key = command.request_key.strip()
        if (
            not request_key
            or not command.first_name.strip()
            or not command.last_name.strip()
        ):
            raise OnboardingConflictError("Required onboarding identity is missing.")
        if (command.login_email is None) == (command.existing_user_id is None):
            raise OnboardingConflictError(
                "Exactly one login identity source is required."
            )
        email = normalize_email(command.login_email) if command.login_email else None
        facts: dict[str, object] = {
            "version": 1,
            "company_id": str(context.company.id),
            "branch_id": str(command.branch_id),
            "first_name": command.first_name.strip(),
            "last_name": command.last_name.strip(),
            "display_name": command.display_name.strip(),
            "employee_type": command.employee_type,
            "prefix": command.employee_number_prefix,
            "width": command.employee_number_width,
            "role_ids": tuple(sorted(str(value) for value in command.role_ids)),
            "login_digest": hashlib.sha256(email.encode()).hexdigest()
            if email
            else None,
            "existing_user_id": str(command.existing_user_id)
            if command.existing_user_id
            else None,
        }
        request_digest = _digest(facts)
        now = datetime.now(timezone.utc)
        try:
            async with session.begin():
                existing = await session.scalar(
                    select(IdentityOnboardingRequest)
                    .where(
                        IdentityOnboardingRequest.company_id == context.company.id,
                        IdentityOnboardingRequest.request_key == request_key,
                    )
                    .with_for_update()
                )
                if existing is not None:
                    if existing.request_digest != request_digest:
                        raise OnboardingConflictError(
                            "Onboarding request identity is already bound."
                        )
                    return existing
                branch = await session.scalar(
                    select(Branch)
                    .where(
                        Branch.id == command.branch_id,
                        Branch.company_id == context.company.id,
                        Branch.status == "active",
                        Branch.archived_at.is_(None),
                    )
                    .with_for_update()
                )
                if branch is None:
                    raise OnboardingConflictError(
                        "Active Company Branch was not found."
                    )
                company_lock = int.from_bytes(
                    context.company.id.bytes[:8], "big", signed=True
                )
                await session.execute(select(func.pg_advisory_xact_lock(company_lock)))
                policy = await session.scalar(
                    select(EmployeeNumberPolicy)
                    .where(EmployeeNumberPolicy.company_id == context.company.id)
                    .with_for_update()
                )
                if policy is None:
                    policy = EmployeeNumberPolicy(
                        company_id=context.company.id,
                        prefix=command.employee_number_prefix,
                        width=command.employee_number_width,
                        next_value=1,
                    )
                    session.add(policy)
                    await session.flush()
                if (
                    policy.prefix != command.employee_number_prefix
                    or policy.width != command.employee_number_width
                ):
                    raise OnboardingConflictError("Employee-number policy conflicts.")
                employee_number = f"{policy.prefix}{policy.next_value:0{policy.width}d}"
                policy.next_value += 1
                policy.updated_at = now
                if command.existing_user_id:
                    user = await session.scalar(
                        select(User)
                        .where(User.id == command.existing_user_id)
                        .with_for_update()
                    )
                    if (
                        user is None
                        or user.status != "active"
                        or user.archived_at is not None
                        or user.email_verified_at is None
                    ):
                        raise OnboardingConflictError(
                            "Eligible existing User was not found."
                        )
                    membership = await session.scalar(
                        select(Membership)
                        .where(
                            Membership.user_id == user.id,
                            Membership.company_id == context.company.id,
                            Membership.status == "active",
                        )
                        .with_for_update()
                    )
                    if membership is None:
                        raise OnboardingConflictError(
                            "Eligible existing Membership was not found."
                        )
                    if not await session.scalar(
                        select(UserCredential.id).where(
                            UserCredential.user_id == user.id
                        )
                    ):
                        raise OnboardingConflictError(
                            "Eligible existing credential was not found."
                        )
                    if await session.scalar(
                        select(Employee.id).where(
                            Employee.membership_id == membership.id
                        )
                    ):
                        raise OnboardingConflictError(
                            "Membership is already linked to an Employee."
                        )
                    issue_invitation = False
                else:
                    assert email is not None
                    if await session.scalar(
                        select(User.id).where(User.normalized_email == email)
                    ):
                        raise OnboardingConflictError("Login identity already exists.")
                    user = User(
                        normalized_email=email,
                        first_name=command.first_name.strip(),
                        last_name=command.last_name.strip(),
                        display_name=command.display_name.strip(),
                        status="invited",
                    )
                    session.add(user)
                    await session.flush()
                    membership = Membership(
                        user_id=user.id,
                        company_id=context.company.id,
                        status="invited",
                        default_branch_id=branch.id,
                        has_all_branch_access=False,
                        invited_at=now,
                    )
                    session.add(membership)
                    await session.flush()
                    session.add(
                        MembershipBranchAccess(
                            membership_id=membership.id,
                            branch_id=branch.id,
                            assigned_by_user_id=context.user.id,
                        )
                    )
                    issue_invitation = True
                employee = Employee(
                    company_id=context.company.id,
                    membership_id=membership.id,
                    home_branch_id=branch.id,
                    employee_number=employee_number,
                    first_name=command.first_name.strip(),
                    last_name=command.last_name.strip(),
                    display_name=command.display_name.strip(),
                    employee_type=command.employee_type,
                    status="active",
                    created_by_user_id=context.user.id,
                    updated_by_user_id=context.user.id,
                )
                session.add(employee)
                await session.flush()
                for role_id in sorted(set(command.role_ids), key=str):
                    role = await session.scalar(
                        select(Role).where(
                            Role.id == role_id,
                            Role.company_id == context.company.id,
                            Role.status == "active",
                            Role.archived_at.is_(None),
                        )
                    )
                    if role is None:
                        raise OnboardingConflictError(
                            "Approved Company role was not found."
                        )
                    existing_assignment = await session.scalar(
                        select(MembershipRole.id).where(
                            MembershipRole.membership_id == membership.id,
                            MembershipRole.role_id == role.id,
                            MembershipRole.revoked_at.is_(None),
                        )
                    )
                    if existing_assignment is None:
                        session.add(
                            MembershipRole(
                                company_id=context.company.id,
                                membership_id=membership.id,
                                role_id=role.id,
                                assigned_by_user_id=context.user.id,
                            )
                        )
                record = IdentityOnboardingRequest(
                    company_id=context.company.id,
                    branch_id=branch.id,
                    employee_id=employee.id,
                    user_id=user.id,
                    membership_id=membership.id,
                    request_key=request_key,
                    request_digest=request_digest,
                    masked_login=_masked(user.normalized_email),
                    status="activated" if not issue_invitation else "invited",
                    initiated_by_user_id=context.user.id,
                    activated_at=now if not issue_invitation else None,
                )
                session.add(record)
                await session.flush()
                if issue_invitation:
                    secret = self.tokens.generate_token()
                    token_hash = self.tokens.hash_token(secret)
                    invitation = IdentityOnboardingInvitation(
                        onboarding_request_id=record.id,
                        token_hash=token_hash,
                        status="pending",
                        issued_by_user_id=context.user.id,
                        issued_at=now,
                        expires_at=now
                        + timedelta(
                            seconds=self.configuration.identity_onboarding_invitation_lifetime_seconds
                        ),
                        safe_digest=_digest(
                            {"request": str(record.id), "token_hash": token_hash}
                        ),
                    )
                    session.add(invitation)
                    await session.flush()
                    nonce = os.urandom(12)
                    ciphertext = cipher.encrypt(
                        nonce, secret.encode(), str(invitation.id).encode()
                    )
                    session.add(
                        ProtectedInvitationDeliveryEnvelope(
                            invitation_id=invitation.id,
                            key_id=key_id,
                            nonce=nonce,
                            ciphertext=ciphertext,
                            status="pending",
                        )
                    )
                    await self._enqueue_delivery(
                        session,
                        company_id=context.company.id,
                        branch_id=branch.id,
                        invitation_id=invitation.id,
                        recipient=user.normalized_email,
                        request_key=f"identity-onboarding:{invitation.id}",
                        now=now,
                    )
                    self._evidence(
                        session,
                        context,
                        record,
                        EventType.IDENTITY_INVITATION_ISSUED,
                    )
                self._evidence(
                    session, context, record, EventType.IDENTITY_ONBOARDING_INITIATED
                )
            return record
        except IntegrityError as error:
            await session.rollback()
            raise OnboardingConflictError(
                "Onboarding identity conflicts with current authority."
            ) from error

    async def activate(
        self, session: AsyncSession, *, token: str, password: str
    ) -> IdentityOnboardingRequest:
        token_hash = self.tokens.hash_token(token)
        now = datetime.now(timezone.utc)
        if await self._mark_expired(session, token_hash=token_hash, now=now):
            raise OnboardingConflictError("Invitation is invalid.")
        async with session.begin():
            invitation = await session.scalar(
                select(IdentityOnboardingInvitation)
                .where(IdentityOnboardingInvitation.token_hash == token_hash)
                .with_for_update()
            )
            if invitation is None or invitation.status != "pending":
                raise OnboardingConflictError("Invitation is invalid.")
            if invitation.expires_at <= now:
                raise OnboardingConflictError("Invitation is invalid.")
            record = await session.scalar(
                select(IdentityOnboardingRequest)
                .where(IdentityOnboardingRequest.id == invitation.onboarding_request_id)
                .with_for_update()
            )
            if record is None or record.status != "invited":
                raise OnboardingConflictError("Invitation is invalid.")
            user = await session.scalar(
                select(User).where(User.id == record.user_id).with_for_update()
            )
            membership = await session.scalar(
                select(Membership)
                .where(Membership.id == record.membership_id)
                .with_for_update()
            )
            employee = await session.scalar(
                select(Employee)
                .where(Employee.id == record.employee_id)
                .with_for_update()
            )
            if (
                user is None
                or membership is None
                or employee is None
                or membership.user_id != user.id
                or membership.company_id != record.company_id
                or employee.company_id != record.company_id
                or employee.membership_id != membership.id
                or membership.default_branch_id != record.branch_id
                or employee.home_branch_id != record.branch_id
            ):
                raise OnboardingConflictError("Invitation scope is invalid.")
            if await session.scalar(
                select(UserCredential.id).where(UserCredential.user_id == user.id)
            ):
                raise OnboardingConflictError("Credential already exists.")
            session.add(
                credential_service.build_initial_credential(
                    user_id=user.id, password=password, now=now
                )
            )
            user.status = "active"
            user.email_verified_at = now
            membership.status = "active"
            membership.accepted_at = now
            invitation.status = "consumed"
            invitation.consumed_at = now
            record.status = "activated"
            record.activated_at = now
            envelope = await session.scalar(
                select(ProtectedInvitationDeliveryEnvelope)
                .where(
                    ProtectedInvitationDeliveryEnvelope.invitation_id == invitation.id
                )
                .with_for_update()
            )
            if envelope is not None:
                envelope.ciphertext = b""
                envelope.nonce = b""
                envelope.status = "destroyed"
                envelope.destroyed_at = now
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.IDENTITY_ONBOARDING_ACTIVATED,
                    entity_type="identity_onboarding",
                    entity_id=record.id,
                    company_id=record.company_id,
                    user_id=user.id,
                    payload={
                        "employee_id": str(employee.id),
                        "membership_id": str(membership.id),
                    },
                ),
            )
            audit_service.stage(
                session,
                AuditEntry(
                    action="identity.onboarding_activated",
                    resource_type="identity_onboarding",
                    resource_id=record.id,
                    actor_user_id=user.id,
                    company_id=record.company_id,
                    branch_id=record.branch_id,
                ),
            )
        return record

    async def claim_protected_delivery(
        self, session: AsyncSession, *, invitation_id: UUID
    ) -> ProtectedInvitationDelivery:
        """Internal provider boundary; never exposed by an HTTP route."""
        now = datetime.now(timezone.utc)
        async with session.begin():
            invitation = await session.scalar(
                select(IdentityOnboardingInvitation)
                .where(IdentityOnboardingInvitation.id == invitation_id)
                .with_for_update()
            )
            envelope = await session.scalar(
                select(ProtectedInvitationDeliveryEnvelope)
                .where(
                    ProtectedInvitationDeliveryEnvelope.invitation_id == invitation_id
                )
                .with_for_update()
            )
            if (
                invitation is None
                or invitation.status != "pending"
                or invitation.expires_at <= now
                or envelope is None
                or envelope.status != "pending"
            ):
                raise OnboardingConflictError("Protected delivery is unavailable.")
            encoded = self.configuration.identity_onboarding_delivery_keys.get(
                envelope.key_id
            )
            if not encoded:
                raise OnboardingConflictError("Protected delivery key is unavailable.")
            try:
                cipher = AESGCM(base64.urlsafe_b64decode(encoded))
                secret = cipher.decrypt(
                    envelope.nonce,
                    envelope.ciphertext,
                    str(invitation.id).encode(),
                ).decode()
            except (ValueError, TypeError) as error:
                raise OnboardingConflictError(
                    "Protected delivery is unavailable."
                ) from error
            request = await session.scalar(
                select(IdentityOnboardingRequest).where(
                    IdentityOnboardingRequest.id == invitation.onboarding_request_id
                )
            )
            user = (
                await session.scalar(select(User).where(User.id == request.user_id))
                if request
                else None
            )
            if request is None or user is None:
                raise OnboardingConflictError(
                    "Protected delivery scope is unavailable."
                )
            envelope.status = "claimed"
            return ProtectedInvitationDelivery(
                invitation.id, user.normalized_email, secret
            )

    async def complete_protected_delivery(
        self, session: AsyncSession, *, invitation_id: UUID
    ) -> None:
        now = datetime.now(timezone.utc)
        async with session.begin():
            envelope = await session.scalar(
                select(ProtectedInvitationDeliveryEnvelope)
                .where(
                    ProtectedInvitationDeliveryEnvelope.invitation_id == invitation_id
                )
                .with_for_update()
            )
            if envelope is None or envelope.status != "claimed":
                raise OnboardingConflictError("Protected delivery is not claimed.")
            envelope.ciphertext = b""
            envelope.nonce = b""
            envelope.status = "delivered"
            envelope.destroyed_at = now

    async def revoke(
        self, session: AsyncSession, *, context: AuthorizationContext, request_id: UUID
    ) -> IdentityOnboardingRequest:
        self._require_admin(context)
        now = datetime.now(timezone.utc)
        async with session.begin():
            record = await session.scalar(
                select(IdentityOnboardingRequest)
                .where(
                    IdentityOnboardingRequest.id == request_id,
                    IdentityOnboardingRequest.company_id == context.company.id,
                )
                .with_for_update()
            )
            if record is None or record.status == "activated":
                raise OnboardingConflictError("Pending onboarding was not found.")
            invitation = await session.scalar(
                select(IdentityOnboardingInvitation)
                .where(
                    IdentityOnboardingInvitation.onboarding_request_id == record.id,
                    IdentityOnboardingInvitation.status == "pending",
                )
                .with_for_update()
            )
            if invitation is not None:
                invitation.status = "revoked"
                invitation.revoked_at = now
                await self._destroy_envelope(session, invitation.id, now)
            record.status = "revoked"
            self._evidence(
                session, context, record, EventType.IDENTITY_INVITATION_REVOKED
            )
        return record

    async def reissue(
        self, session: AsyncSession, *, context: AuthorizationContext, request_id: UUID
    ) -> IdentityOnboardingRequest:
        self._require_admin(context)
        key_id, cipher = self._delivery_cipher()
        now = datetime.now(timezone.utc)
        async with session.begin():
            record = await session.scalar(
                select(IdentityOnboardingRequest)
                .where(
                    IdentityOnboardingRequest.id == request_id,
                    IdentityOnboardingRequest.company_id == context.company.id,
                    IdentityOnboardingRequest.status == "invited",
                )
                .with_for_update()
            )
            if record is None:
                raise OnboardingConflictError("Pending onboarding was not found.")
            prior = await session.scalar(
                select(IdentityOnboardingInvitation)
                .where(
                    IdentityOnboardingInvitation.onboarding_request_id == record.id,
                    IdentityOnboardingInvitation.status == "pending",
                )
                .with_for_update()
            )
            secret = self.tokens.generate_token()
            token_hash = self.tokens.hash_token(secret)
            replacement = IdentityOnboardingInvitation(
                onboarding_request_id=record.id,
                token_hash=token_hash,
                status="pending",
                issued_by_user_id=context.user.id,
                issued_at=now,
                expires_at=now
                + timedelta(
                    seconds=self.configuration.identity_onboarding_invitation_lifetime_seconds
                ),
                safe_digest=_digest(
                    {"request": str(record.id), "token_hash": token_hash}
                ),
            )
            session.add(replacement)
            await session.flush()
            if prior is not None:
                prior.status = "superseded"
                prior.superseded_by_id = replacement.id
                await self._destroy_envelope(session, prior.id, now)
            nonce = os.urandom(12)
            session.add(
                ProtectedInvitationDeliveryEnvelope(
                    invitation_id=replacement.id,
                    key_id=key_id,
                    nonce=nonce,
                    ciphertext=cipher.encrypt(
                        nonce, secret.encode(), str(replacement.id).encode()
                    ),
                    status="pending",
                )
            )
            user = await session.scalar(select(User).where(User.id == record.user_id))
            if user is None:
                raise OnboardingConflictError("Onboarding User was not found.")
            await self._enqueue_delivery(
                session,
                company_id=context.company.id,
                branch_id=record.branch_id,
                invitation_id=replacement.id,
                recipient=user.normalized_email,
                request_key=f"identity-onboarding:{replacement.id}",
                now=now,
            )
            self._evidence(
                session, context, record, EventType.IDENTITY_INVITATION_SUPERSEDED
            )
            self._evidence(
                session, context, record, EventType.IDENTITY_INVITATION_ISSUED
            )
        return record

    async def get(
        self, session: AsyncSession, *, context: AuthorizationContext, request_id: UUID
    ) -> IdentityOnboardingRequest:
        self._require_admin(context)
        record = await session.scalar(
            select(IdentityOnboardingRequest).where(
                IdentityOnboardingRequest.id == request_id,
                IdentityOnboardingRequest.company_id == context.company.id,
            )
        )
        if record is None:
            raise OnboardingConflictError("Onboarding was not found.")
        return record

    async def _destroy_envelope(
        self, session: AsyncSession, invitation_id: UUID, now: datetime
    ) -> None:
        envelope = await session.scalar(
            select(ProtectedInvitationDeliveryEnvelope)
            .where(ProtectedInvitationDeliveryEnvelope.invitation_id == invitation_id)
            .with_for_update()
        )
        if envelope is not None:
            envelope.ciphertext = b""
            envelope.nonce = b""
            envelope.status = "destroyed"
            envelope.destroyed_at = now

    @staticmethod
    async def _mark_expired(
        session: AsyncSession, *, token_hash: str, now: datetime
    ) -> bool:
        """Persist expiry before rejection without ever making a token reusable."""
        async with session.begin():
            invitation = await session.scalar(
                select(IdentityOnboardingInvitation)
                .where(IdentityOnboardingInvitation.token_hash == token_hash)
                .with_for_update()
            )
            if (
                invitation is not None
                and invitation.status == "pending"
                and invitation.expires_at <= now
            ):
                invitation.status = "expired"
                envelope = await session.scalar(
                    select(ProtectedInvitationDeliveryEnvelope)
                    .where(
                        ProtectedInvitationDeliveryEnvelope.invitation_id
                        == invitation.id
                    )
                    .with_for_update()
                )
                if envelope is not None:
                    envelope.ciphertext = b""
                    envelope.nonce = b""
                    envelope.status = "destroyed"
                    envelope.destroyed_at = now
                return True
        return False

    @staticmethod
    async def _enqueue_delivery(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        invitation_id: UUID,
        recipient: str,
        request_key: str,
        now: datetime,
    ) -> None:
        await NotificationOutboxRepository.enqueue(
            session,
            notification_type="identity.onboarding_invitation",
            template_identifier="identity-onboarding-invitation-v1",
            recipient=recipient,
            payload={"invitation_id": str(invitation_id), "protected_envelope": True},
            correlation_id=uuid4(),
            idempotency_key=request_key,
            scheduled_at=now,
            now=now,
            company_id=company_id,
            branch_id=branch_id,
        )

    @staticmethod
    def _evidence(
        session: AsyncSession,
        context: AuthorizationContext,
        record: IdentityOnboardingRequest,
        event_type: EventType,
    ) -> None:
        payload: dict[str, object] = {
            "employee_id": str(record.employee_id),
            "membership_id": str(record.membership_id),
            "status": record.status,
            "request_digest": record.request_digest,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="identity_onboarding",
                entity_id=record.id,
                company_id=record.company_id,
                branch_id=record.branch_id,
                user_id=context.user.id,
                payload=payload,
            ),
        )
        audit_service.stage(
            session,
            AuditEntry(
                action=event_type.value,
                resource_type="identity_onboarding",
                resource_id=record.id,
                actor_user_id=context.user.id,
                company_id=record.company_id,
                branch_id=record.branch_id,
                details=payload,
            ),
        )


identity_onboarding_service = IdentityOnboardingService()
