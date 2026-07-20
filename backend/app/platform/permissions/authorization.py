from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.services import AuthenticatedContext
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential


class AuthorizationError(Exception):
    """Base class for rejected tenant authorization decisions."""


class TenantAccessDeniedError(AuthorizationError):
    pass


class PermissionDeniedError(AuthorizationError):
    pass


@dataclass(frozen=True)
class AuthorizationContext:
    user: User
    company: Company
    membership: Membership
    authorized_branches: tuple[Branch, ...]
    active_branch: Branch | None
    effective_roles: tuple[Role, ...]
    effective_permissions: tuple[Permission, ...]
    credential_version: int
    authorization_version: int

    @property
    def authorized_branch_ids(self) -> frozenset[UUID]:
        return frozenset(branch.id for branch in self.authorized_branches)

    @property
    def role_codes(self) -> frozenset[str]:
        return frozenset(role.code for role in self.effective_roles)

    @property
    def permission_codes(self) -> frozenset[str]:
        return frozenset(permission.code for permission in self.effective_permissions)

    def has_permission(self, permission_code: str) -> bool:
        return permission_code in self.permission_codes

    def can_access_branch(self, branch_id: UUID) -> bool:
        return branch_id in self.authorized_branch_ids


class AuthorizationService:
    """The sole application boundary for tenant authorization decisions."""

    async def resolve(
        self,
        session: AsyncSession,
        *,
        authenticated: AuthenticatedContext,
        company_id: UUID,
        branch_id: UUID | None = None,
    ) -> AuthorizationContext:
        user = await session.scalar(
            select(User).where(User.id == authenticated.user.id)
        )
        credential = await session.scalar(
            select(UserCredential).where(
                UserCredential.user_id == authenticated.user.id
            )
        )
        if (
            user is None
            or credential is None
            or user.status != "active"
            or user.archived_at is not None
            or authenticated.claims.credential_version != credential.credential_version
            or authenticated.claims.authorization_version != user.authorization_version
            or authenticated.authentication_session.credential_version
            != credential.credential_version
            or authenticated.authentication_session.authorization_version
            != user.authorization_version
        ):
            raise TenantAccessDeniedError("Tenant access denied.")

        company = await session.scalar(
            select(Company).where(
                Company.id == company_id,
                Company.status == "active",
                Company.archived_at.is_(None),
            )
        )
        if company is None:
            raise TenantAccessDeniedError("Tenant access denied.")

        membership = await session.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.company_id == company.id,
                Membership.status == "active",
            )
        )
        if membership is None:
            raise TenantAccessDeniedError("Tenant access denied.")

        authorized_branches = await self._resolve_branches(
            session,
            membership=membership,
            company_id=company.id,
        )
        authorized_branch_ids = {branch.id for branch in authorized_branches}
        active_branch: Branch | None = None
        if branch_id is not None:
            active_branch = next(
                (branch for branch in authorized_branches if branch.id == branch_id),
                None,
            )
            if active_branch is None or branch_id not in authorized_branch_ids:
                raise TenantAccessDeniedError("Branch access denied.")

        effective_roles = tuple(
            (
                await session.scalars(
                    select(Role)
                    .join(
                        MembershipRole,
                        MembershipRole.role_id == Role.id,
                    )
                    .where(
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.company_id == company.id,
                        MembershipRole.revoked_at.is_(None),
                        Role.company_id == company.id,
                        Role.status == "active",
                        Role.archived_at.is_(None),
                    )
                    .order_by(Role.code, Role.id)
                )
            )
            .unique()
            .all()
        )
        effective_permissions = tuple(
            (
                await session.scalars(
                    select(Permission)
                    .join(
                        RolePermission,
                        RolePermission.permission_id == Permission.id,
                    )
                    .join(Role, Role.id == RolePermission.role_id)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.company_id == company.id,
                        MembershipRole.revoked_at.is_(None),
                        Role.company_id == company.id,
                        Role.status == "active",
                        Role.archived_at.is_(None),
                        Permission.status == "active",
                        Permission.retired_at.is_(None),
                    )
                    .order_by(Permission.code, Permission.id)
                )
            )
            .unique()
            .all()
        )

        return AuthorizationContext(
            user=user,
            company=company,
            membership=membership,
            authorized_branches=authorized_branches,
            active_branch=active_branch,
            effective_roles=effective_roles,
            effective_permissions=effective_permissions,
            credential_version=credential.credential_version,
            authorization_version=user.authorization_version,
        )

    async def _resolve_branches(
        self,
        session: AsyncSession,
        *,
        membership: Membership,
        company_id: UUID,
    ) -> tuple[Branch, ...]:
        statement = select(Branch).where(
            Branch.company_id == company_id,
            Branch.status == "active",
            Branch.archived_at.is_(None),
        )
        if not membership.has_all_branch_access:
            statement = statement.join(
                MembershipBranchAccess,
                MembershipBranchAccess.branch_id == Branch.id,
            ).where(MembershipBranchAccess.membership_id == membership.id)
        return tuple(
            (await session.scalars(statement.order_by(Branch.code, Branch.id)))
            .unique()
            .all()
        )

    @staticmethod
    def require_permission(
        context: AuthorizationContext,
        permission_code: str,
    ) -> None:
        if not context.has_permission(permission_code):
            raise PermissionDeniedError("Permission denied.")

    @staticmethod
    def require_branch(
        context: AuthorizationContext,
        branch_id: UUID,
    ) -> None:
        if not context.can_access_branch(branch_id):
            raise TenantAccessDeniedError("Branch access denied.")


authorization_service = AuthorizationService()
