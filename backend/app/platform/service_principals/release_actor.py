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
from app.platform.permissions.codes import ReleasePrincipalPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.service_principals.models import ReleaseServicePrincipal
from app.platform.users.models import User, UserCredential

RELEASE_ROLE_CODE = "BETA_RELEASE_ACCEPTANCE_PRINCIPAL_MANAGER"
RELEASE_AUTHENTICATION_METHOD = "release_service_principal"
MAX_RELEASE_SESSION_LIFETIME = timedelta(hours=1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ReleaseActorSession:
    principal_id: UUID
    session_id: UUID
    access_token: str
    expires_at: datetime


class ReleaseActorService:
    """Trusted Release bootstrap into canonical, short-lived application auth."""

    @staticmethod
    def _environment(configuration: Settings) -> str:
        environment = configuration.environment.strip().lower()
        if environment not in {"beta", "preview", "test"}:
            raise ValueError("Release actors are forbidden in this environment.")
        return environment

    async def provision_and_rotate(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        configuration: Settings = settings,
        lifetime: timedelta = MAX_RELEASE_SESSION_LIFETIME,
        now: datetime | None = None,
    ) -> ReleaseActorSession:
        environment = self._environment(configuration)
        if lifetime <= timedelta(0) or lifetime > MAX_RELEASE_SESSION_LIFETIME:
            raise ValueError("Release actor session lifetime is invalid.")
        occurred_at = now or utc_now()
        permission = await session.scalar(
            select(Permission).where(
                Permission.code == ReleasePrincipalPermission.MANAGE
            )
        )
        if permission is None:
            permission = Permission(
                code=ReleasePrincipalPermission.MANAGE,
                name="Acceptance Principal Management",
                description="Provision and revoke bounded acceptance principals",
                resource="acceptance_service_principal",
                action="manage",
                status="active",
            )
            session.add(permission)
            await session.flush()
        elif permission.status != "active":
            raise ValueError("Release actor permission is unavailable.")

        principal = await session.scalar(
            select(ReleaseServicePrincipal)
            .where(
                ReleaseServicePrincipal.company_id == company_id,
                ReleaseServicePrincipal.environment == environment,
            )
            .with_for_update()
        )
        user: User
        credential: UserCredential
        if principal is None:
            user = User(
                normalized_email=(
                    f"release-acceptance+{company_id}@service.twelve-hats.invalid"
                ),
                first_name="Release",
                last_name="Actor",
                display_name="Beta acceptance Release actor",
                status="active",
                authorization_version=1,
                email_verified_at=occurred_at,
            )
            session.add(user)
            await session.flush()
            credential = UserCredential(
                user_id=user.id,
                password_hash=password_service.hash_password(secrets.token_urlsafe(64)),
                password_changed_at=occurred_at,
                credential_version=1,
            )
            session.add(credential)
            membership = Membership(
                user_id=user.id,
                company_id=company_id,
                status="active",
                default_branch_id=None,
                has_all_branch_access=False,
                accepted_at=occurred_at,
            )
            session.add(membership)
            await session.flush()
            role = Role(
                company_id=company_id,
                code=RELEASE_ROLE_CODE,
                name="Beta acceptance Release actor",
                description="Non-human acceptance-principal lifecycle authority",
                status="active",
                is_system=True,
                created_by_user_id=user.id,
                updated_by_user_id=user.id,
            )
            session.add(role)
            await session.flush()
            session.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    assigned_by_user_id=user.id,
                )
            )
            session.add(
                MembershipRole(
                    company_id=company_id,
                    membership_id=membership.id,
                    role_id=role.id,
                    assigned_by_user_id=user.id,
                    assigned_at=occurred_at,
                    grant_reason="release_acceptance_principal_management",
                )
            )
            principal = ReleaseServicePrincipal(
                company_id=company_id,
                user_id=user.id,
                membership_id=membership.id,
                environment=environment,
                state="active",
                version=1,
                created_at=occurred_at,
                updated_at=occurred_at,
            )
            session.add(principal)
            await session.flush()
        else:
            if principal.state != "active":
                raise ValueError("Release actor is revoked.")
            existing_user = await session.get(User, principal.user_id)
            existing_credential = await session.scalar(
                select(UserCredential)
                .where(UserCredential.user_id == principal.user_id)
                .with_for_update()
            )
            if (
                existing_user is None
                or existing_credential is None
                or existing_user.status != "active"
            ):
                raise ValueError("Release actor identity is incomplete.")
            user = existing_user
            credential = existing_credential
            await self._assert_exact_permission(session, principal.membership_id)
            principal.version += 1
            principal.updated_at = occurred_at
            user.authorization_version += 1
            credential.credential_version += 1
            active_sessions = (
                await session.scalars(
                    select(AuthenticationSession).where(
                        AuthenticationSession.user_id == user.id,
                        AuthenticationSession.status == "active",
                    )
                )
            ).all()
            for old_session in active_sessions:
                old_session.status = "revoked"
                old_session.revoked_at = occurred_at
                old_session.revocation_reason = "release_actor_rotated"
                old_session.revoked_by_user_id = user.id

        auth_session = AuthenticationSession(
            user_id=user.id,
            status="active",
            created_at=occurred_at,
            last_seen_at=occurred_at,
            absolute_expires_at=occurred_at + lifetime,
            idle_expires_at=None,
            authentication_method=RELEASE_AUTHENTICATION_METHOD,
            credential_version=credential.credential_version,
            authorization_version=user.authorization_version,
            device_label="beta-release-acceptance-provisioner",
        )
        session.add(auth_session)
        await session.flush()
        token, token_expiry = access_token_service.issue(
            user_id=user.id,
            session_id=auth_session.id,
            credential_version=credential.credential_version,
            authorization_version=user.authorization_version,
            now=occurred_at,
        )
        expires_at = min(token_expiry, auth_session.absolute_expires_at)
        audit_service.stage(
            session,
            AuditEntry(
                action="platform.release_actor_session_issued",
                resource_type="release_service_principal",
                resource_id=principal.id,
                actor_user_id=user.id,
                company_id=company_id,
                details={"environment": environment, "expires_at": expires_at.isoformat()},
            ),
        )
        return ReleaseActorSession(principal.id, auth_session.id, token, expires_at)

    async def revoke(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        configuration: Settings = settings,
        now: datetime | None = None,
    ) -> UUID:
        environment = self._environment(configuration)
        occurred_at = now or utc_now()
        principal = await session.scalar(
            select(ReleaseServicePrincipal)
            .where(
                ReleaseServicePrincipal.company_id == company_id,
                ReleaseServicePrincipal.environment == environment,
            )
            .with_for_update()
        )
        if principal is None:
            raise ValueError("Release actor was not found.")
        if principal.state == "revoked":
            return principal.id
        user = await session.get(User, principal.user_id)
        credential = await session.scalar(
            select(UserCredential)
            .where(UserCredential.user_id == principal.user_id)
            .with_for_update()
        )
        if user is None or credential is None:
            raise ValueError("Release actor identity is incomplete.")
        principal.state = "revoked"
        principal.version += 1
        principal.revoked_at = occurred_at
        principal.updated_at = occurred_at
        user.status = "disabled"
        user.authorization_version += 1
        credential.credential_version += 1
        active_sessions = (
            await session.scalars(
                select(AuthenticationSession).where(
                    AuthenticationSession.user_id == user.id,
                    AuthenticationSession.status == "active",
                )
            )
        ).all()
        for active_session in active_sessions:
            active_session.status = "revoked"
            active_session.revoked_at = occurred_at
            active_session.revocation_reason = "release_actor_revoked"
            active_session.revoked_by_user_id = user.id
        audit_service.stage(
            session,
            AuditEntry(
                action="platform.release_actor_revoked",
                resource_type="release_service_principal",
                resource_id=principal.id,
                actor_user_id=user.id,
                company_id=company_id,
                details={"environment": environment},
            ),
        )
        return principal.id

    @staticmethod
    async def _assert_exact_permission(
        session: AsyncSession, membership_id: UUID
    ) -> None:
        codes = set(
            (
                await session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
                    .where(
                        MembershipRole.membership_id == membership_id,
                        MembershipRole.revoked_at.is_(None),
                        Permission.status == "active",
                    )
                )
            ).all()
        )
        if codes != {ReleasePrincipalPermission.MANAGE}:
            raise ValueError("Release actor permission set is not exact.")


release_actor_service = ReleaseActorService()
