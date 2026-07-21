from dataclasses import dataclass
from datetime import datetime
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
class AuthorizedUser:
    id: UUID
    normalized_email: str
    first_name: str
    last_name: str
    display_name: str
    status: str
    authorization_version: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None
    email_verified_at: datetime | None
    archived_at: datetime | None


@dataclass(frozen=True)
class AuthorizedCompany:
    id: UUID
    name: str
    code: str
    status: str
    timezone: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True)
class AuthorizedMembership:
    id: UUID
    user_id: UUID
    company_id: UUID
    status: str
    default_branch_id: UUID | None
    has_all_branch_access: bool
    invited_at: datetime | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    revoked_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AuthorizedBranch:
    id: UUID
    company_id: UUID
    name: str
    code: str
    status: str
    timezone: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True)
class AuthorizedRole:
    id: UUID
    company_id: UUID
    code: str
    name: str
    description: str | None
    status: str
    is_system: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None


@dataclass(frozen=True)
class AuthorizedPermission:
    id: UUID
    code: str
    name: str
    description: str | None
    resource: str
    action: str
    status: str
    created_at: datetime
    updated_at: datetime
    retired_at: datetime | None


@dataclass(frozen=True, init=False)
class AuthorizationContext:
    user: AuthorizedUser
    company: AuthorizedCompany
    membership: AuthorizedMembership
    authorized_branches: tuple[AuthorizedBranch, ...]
    active_branch: AuthorizedBranch | None
    effective_roles: tuple[AuthorizedRole, ...]
    effective_permissions: tuple[AuthorizedPermission, ...]
    credential_version: int
    authorization_version: int

    def __init__(
        self,
        user: User | AuthorizedUser,
        company: Company | AuthorizedCompany,
        membership: Membership | AuthorizedMembership,
        authorized_branches: tuple[Branch | AuthorizedBranch, ...],
        active_branch: Branch | AuthorizedBranch | None,
        effective_roles: tuple[Role | AuthorizedRole, ...],
        effective_permissions: tuple[Permission | AuthorizedPermission, ...],
        credential_version: int,
        authorization_version: int,
    ) -> None:
        object.__setattr__(self, "user", _authorized_user(user))
        object.__setattr__(self, "company", _authorized_company(company))
        object.__setattr__(self, "membership", _authorized_membership(membership))
        object.__setattr__(
            self,
            "authorized_branches",
            tuple(_authorized_branch(branch) for branch in authorized_branches),
        )
        object.__setattr__(
            self,
            "active_branch",
            _authorized_branch(active_branch) if active_branch is not None else None,
        )
        object.__setattr__(
            self,
            "effective_roles",
            tuple(_authorized_role(role) for role in effective_roles),
        )
        object.__setattr__(
            self,
            "effective_permissions",
            tuple(
                _authorized_permission(permission)
                for permission in effective_permissions
            ),
        )
        object.__setattr__(self, "credential_version", credential_version)
        object.__setattr__(self, "authorization_version", authorization_version)

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


def _authorized_user(value: User | AuthorizedUser) -> AuthorizedUser:
    if isinstance(value, AuthorizedUser):
        return value
    return AuthorizedUser(
        id=value.id,
        normalized_email=value.normalized_email,
        first_name=value.first_name,
        last_name=value.last_name,
        display_name=value.display_name,
        status=value.status,
        authorization_version=value.authorization_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
        disabled_at=value.disabled_at,
        email_verified_at=value.email_verified_at,
        archived_at=value.archived_at,
    )


def _authorized_company(value: Company | AuthorizedCompany) -> AuthorizedCompany:
    if isinstance(value, AuthorizedCompany):
        return value
    return AuthorizedCompany(
        id=value.id,
        name=value.name,
        code=value.code,
        status=value.status,
        timezone=value.timezone,
        created_at=value.created_at,
        updated_at=value.updated_at,
        archived_at=value.archived_at,
    )


def _authorized_membership(
    value: Membership | AuthorizedMembership,
) -> AuthorizedMembership:
    if isinstance(value, AuthorizedMembership):
        return value
    return AuthorizedMembership(
        id=value.id,
        user_id=value.user_id,
        company_id=value.company_id,
        status=value.status,
        default_branch_id=value.default_branch_id,
        has_all_branch_access=value.has_all_branch_access,
        invited_at=value.invited_at,
        accepted_at=value.accepted_at,
        revoked_at=value.revoked_at,
        revoked_by_user_id=value.revoked_by_user_id,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _authorized_branch(value: Branch | AuthorizedBranch) -> AuthorizedBranch:
    if isinstance(value, AuthorizedBranch):
        return value
    return AuthorizedBranch(
        id=value.id,
        company_id=value.company_id,
        name=value.name,
        code=value.code,
        status=value.status,
        timezone=value.timezone,
        is_primary=value.is_primary,
        created_at=value.created_at,
        updated_at=value.updated_at,
        archived_at=value.archived_at,
    )


def _authorized_role(value: Role | AuthorizedRole) -> AuthorizedRole:
    if isinstance(value, AuthorizedRole):
        return value
    return AuthorizedRole(
        id=value.id,
        company_id=value.company_id,
        code=value.code,
        name=value.name,
        description=value.description,
        status=value.status,
        is_system=value.is_system,
        created_at=value.created_at,
        updated_at=value.updated_at,
        archived_at=value.archived_at,
        created_by_user_id=value.created_by_user_id,
        updated_by_user_id=value.updated_by_user_id,
    )


def _authorized_permission(
    value: Permission | AuthorizedPermission,
) -> AuthorizedPermission:
    if isinstance(value, AuthorizedPermission):
        return value
    return AuthorizedPermission(
        id=value.id,
        code=value.code,
        name=value.name,
        description=value.description,
        resource=value.resource,
        action=value.action,
        status=value.status,
        created_at=value.created_at,
        updated_at=value.updated_at,
        retired_at=value.retired_at,
    )


@dataclass(frozen=True)
class AccessibleCompany:
    company: Company
    membership: Membership
    authorized_branches: tuple[Branch, ...]


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

    async def list_accessible_companies(
        self,
        session: AsyncSession,
        *,
        authenticated: AuthenticatedContext,
    ) -> tuple[AccessibleCompany, ...]:
        memberships = tuple(
            (
                await session.scalars(
                    select(Membership)
                    .join(Company, Company.id == Membership.company_id)
                    .where(
                        Membership.user_id == authenticated.user.id,
                        Membership.status == "active",
                        Company.status == "active",
                        Company.archived_at.is_(None),
                    )
                    .order_by(Company.name, Company.id)
                )
            )
            .unique()
            .all()
        )
        access: list[AccessibleCompany] = []
        for membership in memberships:
            company = await session.get(Company, membership.company_id)
            if company is None:
                continue
            access.append(
                AccessibleCompany(
                    company=company,
                    membership=membership,
                    authorized_branches=await self._resolve_branches(
                        session,
                        membership=membership,
                        company_id=company.id,
                    ),
                )
            )
        return tuple(access)

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
