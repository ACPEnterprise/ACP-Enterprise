from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import access_token_service, password_service
from app.platform.company.membership_models import Membership
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import WorkerIdentityPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.service_principals.contracts import (
    AUTHENTICATION_METHOD,
    READ_PERMISSION_CODES,
    ROLE_CODE,
)
from app.platform.service_principals.models import AcceptanceServicePrincipal
from app.platform.users.models import User, UserCredential

MAX_ACCESS_LIFETIME = timedelta(hours=1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PrincipalProvisioningResult:
    principal_id: UUID
    user_id: UUID
    membership_id: UUID
    created: bool


@dataclass(frozen=True, slots=True)
class PrincipalSessionResult:
    principal_id: UUID
    session_id: UUID
    access_token: str
    expires_at: datetime


class AcceptanceServicePrincipalService:
    @staticmethod
    def _require_platform_authority(context: AuthorizationContext) -> None:
        if context.membership.status != "active" or not context.has_permission(
            WorkerIdentityPermission.MANAGE
        ):
            raise PermissionError("Platform service-principal authority is required.")

    async def provision(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        name: str = "Beta acceptance reader",
        configuration: Settings = settings,
        now: datetime | None = None,
    ) -> PrincipalProvisioningResult:
        self._require_platform_authority(context)
        occurred_at = now or utc_now()
        environment = configuration.environment.strip().lower()
        if environment not in {"preview", "beta", "test"}:
            raise ValueError(
                "Acceptance service principals are not provisioned in this environment."
            )
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 100:
            raise ValueError("Service-principal name is invalid.")
        existing = await session.scalar(
            select(AcceptanceServicePrincipal).where(
                AcceptanceServicePrincipal.company_id == context.company.id,
                AcceptanceServicePrincipal.environment == environment,
                AcceptanceServicePrincipal.name == normalized_name,
            )
        )
        if existing is not None:
            if existing.state != "active":
                raise ValueError("Service principal is revoked.")
            await self._assert_exact_permissions(session, existing.membership_id)
            return PrincipalProvisioningResult(
                existing.id, existing.user_id, existing.membership_id, False
            )

        permissions = tuple(
            (
                await session.scalars(
                    select(Permission).where(
                        Permission.code.in_(READ_PERMISSION_CODES),
                        Permission.status == "active",
                    )
                )
            ).all()
        )
        if {item.code for item in permissions} != READ_PERMISSION_CODES:
            raise ValueError("Required read-only permission catalog is incomplete.")
        role = await session.scalar(
            select(Role).where(
                Role.company_id == context.company.id,
                Role.code == ROLE_CODE,
                Role.archived_at.is_(None),
            )
        )
        if role is None:
            role = Role(
                company_id=context.company.id,
                code=ROLE_CODE,
                name="Acceptance read-only service",
                description="Non-human release acceptance reader",
                status="active",
                is_system=True,
                created_by_user_id=context.user.id,
                updated_by_user_id=context.user.id,
            )
            session.add(role)
            await session.flush()
            for permission in permissions:
                session.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission.id,
                        assigned_by_user_id=context.user.id,
                    )
                )
        else:
            assigned = set(
                (
                    await session.scalars(
                        select(Permission.code)
                        .join(
                            RolePermission,
                            RolePermission.permission_id == Permission.id,
                        )
                        .where(RolePermission.role_id == role.id)
                    )
                ).all()
            )
            if assigned != READ_PERMISSION_CODES:
                raise ValueError("Acceptance service role permission set is not exact.")

        user = User(
            normalized_email=f"acceptance+{context.company.id}@service.twelve-hats.invalid",
            first_name="Acceptance",
            last_name="Reader",
            display_name=normalized_name,
            status="active",
            authorization_version=1,
            email_verified_at=occurred_at,
        )
        session.add(user)
        await session.flush()
        session.add(
            UserCredential(
                user_id=user.id,
                password_hash=password_service.hash_password(secrets.token_urlsafe(64)),
                password_changed_at=occurred_at,
                credential_version=1,
            )
        )
        membership = Membership(
            user_id=user.id,
            company_id=context.company.id,
            status="active",
            default_branch_id=context.membership.default_branch_id,
            has_all_branch_access=True,
            accepted_at=occurred_at,
        )
        session.add(membership)
        await session.flush()
        session.add(
            MembershipRole(
                company_id=context.company.id,
                membership_id=membership.id,
                role_id=role.id,
                assigned_by_user_id=context.user.id,
                assigned_at=occurred_at,
                grant_reason="release_acceptance_readonly",
            )
        )
        principal = AcceptanceServicePrincipal(
            company_id=context.company.id,
            user_id=user.id,
            membership_id=membership.id,
            name=normalized_name,
            environment=environment,
            state="active",
            version=1,
            provisioned_by_user_id=context.user.id,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        session.add(principal)
        await session.flush()
        audit_service.stage(
            session,
            AuditEntry(
                action="platform.acceptance_service_principal_provisioned",
                resource_type="acceptance_service_principal",
                resource_id=principal.id,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                details={
                    "environment": environment,
                    "permission_count": len(READ_PERMISSION_CODES),
                },
            ),
        )
        return PrincipalProvisioningResult(principal.id, user.id, membership.id, True)

    async def issue_session(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        principal_id: UUID,
        lifetime: timedelta = MAX_ACCESS_LIFETIME,
        configuration: Settings = settings,
        now: datetime | None = None,
    ) -> PrincipalSessionResult:
        self._require_platform_authority(context)
        if lifetime <= timedelta(0) or lifetime > MAX_ACCESS_LIFETIME:
            raise ValueError("Service-principal session lifetime is invalid.")
        occurred_at = now or utc_now()
        principal = await session.scalar(
            select(AcceptanceServicePrincipal)
            .where(
                AcceptanceServicePrincipal.id == principal_id,
                AcceptanceServicePrincipal.company_id == context.company.id,
            )
            .with_for_update()
        )
        if (
            principal is None
            or principal.state != "active"
            or principal.environment != configuration.environment.strip().lower()
        ):
            raise ValueError("Service principal is unavailable in this environment.")
        await self._assert_exact_permissions(session, principal.membership_id)
        user = await session.get(User, principal.user_id)
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == principal.user_id)
        )
        if (
            user is None
            or credential is None
            or user.status != "active"
            or credential.credential_version != principal.version
        ):
            raise ValueError("Service principal version binding is invalid.")
        auth_session = AuthenticationSession(
            user_id=user.id,
            status="active",
            created_at=occurred_at,
            last_seen_at=occurred_at,
            absolute_expires_at=occurred_at + lifetime,
            idle_expires_at=None,
            authentication_method=AUTHENTICATION_METHOD,
            credential_version=principal.version,
            authorization_version=user.authorization_version,
            device_label="release-acceptance-readonly",
        )
        session.add(auth_session)
        await session.flush()
        token, token_expiry = access_token_service.issue(
            user_id=user.id,
            session_id=auth_session.id,
            credential_version=principal.version,
            authorization_version=user.authorization_version,
            now=occurred_at,
        )
        expires_at = min(token_expiry, auth_session.absolute_expires_at)
        audit_service.stage(
            session,
            AuditEntry(
                action="platform.acceptance_service_session_issued",
                resource_type="authentication_session",
                resource_id=auth_session.id,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                details={
                    "principal_id": str(principal.id),
                    "environment": principal.environment,
                    "expires_at": expires_at.isoformat(),
                },
            ),
        )
        return PrincipalSessionResult(principal.id, auth_session.id, token, expires_at)

    async def revoke(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        principal_id: UUID,
        now: datetime | None = None,
    ) -> None:
        self._require_platform_authority(context)
        occurred_at = now or utc_now()
        principal = await session.scalar(
            select(AcceptanceServicePrincipal)
            .where(
                AcceptanceServicePrincipal.id == principal_id,
                AcceptanceServicePrincipal.company_id == context.company.id,
            )
            .with_for_update()
        )
        if principal is None:
            raise ValueError("Service principal was not found.")
        if principal.state == "revoked":
            return
        principal.state = "revoked"
        principal.version += 1
        principal.revoked_at = occurred_at
        principal.updated_at = occurred_at
        user = await session.get(User, principal.user_id)
        credential = await session.scalar(
            select(UserCredential)
            .where(UserCredential.user_id == principal.user_id)
            .with_for_update()
        )
        if user is None or credential is None:
            raise ValueError("Service principal identity is incomplete.")
        user.authorization_version += 1
        user.status = "disabled"
        credential.credential_version += 1
        sessions = (
            await session.scalars(
                select(AuthenticationSession)
                .where(
                    AuthenticationSession.user_id == user.id,
                    AuthenticationSession.status == "active",
                )
                .with_for_update()
            )
        ).all()
        for auth_session in sessions:
            auth_session.status = "revoked"
            auth_session.revoked_at = occurred_at
            auth_session.revocation_reason = "service_principal_revoked"
            auth_session.revoked_by_user_id = context.user.id
        audit_service.stage(
            session,
            AuditEntry(
                action="platform.acceptance_service_principal_revoked",
                resource_type="acceptance_service_principal",
                resource_id=principal.id,
                actor_user_id=context.user.id,
                company_id=context.company.id,
            ),
        )

    @staticmethod
    async def _assert_exact_permissions(
        session: AsyncSession, membership_id: UUID
    ) -> None:
        codes = set(
            (
                await session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .join(Role, Role.id == RolePermission.role_id)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(
                        MembershipRole.membership_id == membership_id,
                        MembershipRole.revoked_at.is_(None),
                        Role.status == "active",
                        Role.archived_at.is_(None),
                        Permission.status == "active",
                    )
                )
            ).all()
        )
        if codes != READ_PERMISSION_CODES:
            raise ValueError("Service principal permission set is not exact.")


acceptance_service_principal_service = AcceptanceServicePrincipalService()
