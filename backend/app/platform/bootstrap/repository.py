from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX
from app.platform.permissions.catalog import PermissionDefinition
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential

BOOTSTRAP_ADVISORY_LOCK_ID = 4_701_871_310_042_021


class BootstrapRepository:
    """Owns persistence and the PostgreSQL serialization boundary for bootstrap."""

    async def acquire_initialization_lock(self, session: AsyncSession) -> None:
        await session.execute(
            select(func.pg_advisory_xact_lock(BOOTSTRAP_ADVISORY_LOCK_ID))
        )

    async def is_initialized(self, session: AsyncSession) -> bool:
        return bool(await session.scalar(select(func.count()).select_from(Company)))

    def create_company(
        self,
        session: AsyncSession,
        *,
        name: str,
        code: str,
        timezone: str,
    ) -> Company:
        company = Company(name=name, code=code, status="active", timezone=timezone)
        session.add(company)
        return company

    def create_branch(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        name: str,
        code: str,
        timezone: str,
    ) -> Branch:
        branch = Branch(
            company_id=company_id,
            name=name,
            code=code,
            status="active",
            timezone=timezone,
            is_primary=True,
        )
        session.add(branch)
        return branch

    def create_administrator(
        self,
        session: AsyncSession,
        *,
        email: str,
        first_name: str,
        last_name: str,
        display_name: str,
        password_hash: str,
        now: datetime,
    ) -> User:
        user = User(
            normalized_email=email,
            first_name=first_name,
            last_name=last_name,
            display_name=display_name,
            status="active",
            authorization_version=1,
            email_verified_at=now,
        )
        session.add(user)
        session.add(
            UserCredential(
                user=user,
                password_hash=password_hash,
                password_changed_at=now,
                failed_login_count=0,
                credential_version=1,
            )
        )
        return user

    def create_membership(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        now: datetime,
    ) -> Membership:
        membership = Membership(
            user_id=user_id,
            company_id=company_id,
            status="active",
            default_branch_id=branch_id,
            has_all_branch_access=True,
            invited_at=now,
            accepted_at=now,
        )
        session.add(membership)
        return membership

    def create_permissions(
        self,
        session: AsyncSession,
        definitions: Iterable[PermissionDefinition],
    ) -> dict[str, Permission]:
        permissions = {
            definition.code: Permission(
                code=definition.code,
                name=definition.name,
                description=None,
                resource=definition.resource,
                action=definition.action,
                status="active",
            )
            for definition in definitions
        }
        session.add_all(permissions.values())
        return permissions

    def create_system_roles(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        actor_user_id: UUID,
    ) -> dict[str, Role]:
        roles = {
            role.code.value: Role(
                company_id=company_id,
                code=role.code.value,
                name=role.code.value.replace("_", " ").title(),
                description=role.purpose,
                status="active",
                is_system=True,
                created_by_user_id=actor_user_id,
                updated_by_user_id=actor_user_id,
            )
            for role in LAUNCH_ROLE_MATRIX
        }
        roles["COMPANY_USER"] = Role(
            company_id=company_id,
            code="COMPANY_USER",
            name="Company User",
            description="Baseline system role with no implicit capabilities.",
            status="active",
            is_system=True,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        session.add_all(roles.values())
        return roles

    def assign_permissions(
        self,
        session: AsyncSession,
        *,
        role: Role,
        permissions: Iterable[Permission],
        actor_user_id: UUID,
        now: datetime,
    ) -> None:
        session.add_all(
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                assigned_at=now,
                assigned_by_user_id=actor_user_id,
            )
            for permission in permissions
        )

    def assign_role(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        membership_id: UUID,
        role_id: UUID,
        actor_user_id: UUID,
        now: datetime,
    ) -> None:
        session.add(
            MembershipRole(
                company_id=company_id,
                membership_id=membership_id,
                role_id=role_id,
                assigned_at=now,
                assigned_by_user_id=actor_user_id,
            )
        )
