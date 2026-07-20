from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccessPolicyAdministrationError(Exception):
    pass


class AccessPolicyNotFoundError(AccessPolicyAdministrationError):
    pass


class AccessPolicyConflictError(AccessPolicyAdministrationError):
    pass


class FinalAdministratorError(AccessPolicyConflictError):
    pass


class CompanyAdministrationService:
    async def list_memberships(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
    ) -> list[Membership]:
        return list(
            (
                await session.scalars(
                    select(Membership)
                    .where(Membership.company_id == context.company.id)
                    .order_by(Membership.created_at, Membership.id)
                )
            ).all()
        )

    async def create_membership(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        user_id: UUID,
        status: str = "invited",
        default_branch_id: UUID | None = None,
        has_all_branch_access: bool = False,
    ) -> Membership:
        if status not in {"invited", "active"}:
            raise AccessPolicyConflictError("Membership status is invalid.")
        now = utc_now()
        async with session.begin():
            await self._lock_company(session, context)
            user = await session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None or user.status != "active" or user.archived_at is not None:
                raise AccessPolicyNotFoundError("Eligible User was not found.")
            existing = await session.scalar(
                select(Membership)
                .where(
                    Membership.user_id == user_id,
                    Membership.company_id == context.company.id,
                )
                .with_for_update()
            )
            if existing is not None:
                if (
                    existing.status == status
                    and existing.default_branch_id == default_branch_id
                    and existing.has_all_branch_access == has_all_branch_access
                ):
                    return existing
                raise AccessPolicyConflictError("Membership already exists.")
            if default_branch_id is not None:
                await self._require_active_branch(
                    session, company_id=context.company.id, branch_id=default_branch_id
                )
            membership = Membership(
                user_id=user_id,
                company_id=context.company.id,
                status=status,
                default_branch_id=default_branch_id,
                has_all_branch_access=has_all_branch_access,
                invited_at=now,
                accepted_at=now if status == "active" else None,
            )
            session.add(membership)
            await session.flush()
            await self._increment_user_versions(session, {user_id})
            self._stage_event(
                session,
                context=context,
                event_type=EventType.MEMBERSHIP_CREATED,
                entity_id=membership.id,
                payload={"status": status},
            )
        return membership

    async def set_membership_status(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        membership_id: UUID,
        status: str,
    ) -> Membership:
        if status not in {"active", "suspended", "revoked"}:
            raise AccessPolicyConflictError("Membership status is invalid.")
        now = utc_now()
        async with session.begin():
            await self._lock_company(session, context)
            membership = await self._membership_for_update(
                session, context.company.id, membership_id
            )
            if membership.status == status:
                return membership
            user = await session.scalar(
                select(User).where(User.id == membership.user_id).with_for_update()
            )
            if user is None:
                raise AccessPolicyNotFoundError("Membership was not found.")
            if status == "active" and (
                user.status != "active" or user.archived_at is not None
            ):
                raise AccessPolicyConflictError("User is not eligible for access.")
            if status in {"suspended", "revoked"} and membership.status == "active":
                await self._guard_membership_is_not_final_admin(
                    session,
                    company_id=context.company.id,
                    membership_id=membership.id,
                )
            membership.status = status
            membership.updated_at = now
            if status == "active":
                membership.accepted_at = membership.accepted_at or now
                membership.revoked_at = None
                membership.revoked_by_user_id = None
            elif status == "revoked":
                membership.revoked_at = now
                membership.revoked_by_user_id = context.user.id
            await self._increment_user_versions(session, {membership.user_id})
            event_type = {
                "active": EventType.MEMBERSHIP_ACTIVATED,
                "suspended": EventType.MEMBERSHIP_SUSPENDED,
                "revoked": EventType.MEMBERSHIP_REVOKED,
            }[status]
            self._stage_event(
                session,
                context=context,
                event_type=event_type,
                entity_id=membership.id,
                payload={"status": status},
            )
        return membership

    async def add_branch_access(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        membership_id: UUID,
        branch_id: UUID,
    ) -> MembershipBranchAccess:
        now = utc_now()
        async with session.begin():
            await self._lock_company(session, context)
            membership = await self._membership_for_update(
                session, context.company.id, membership_id
            )
            await self._require_active_branch(
                session, company_id=context.company.id, branch_id=branch_id
            )
            existing = await session.scalar(
                select(MembershipBranchAccess)
                .where(
                    MembershipBranchAccess.membership_id == membership.id,
                    MembershipBranchAccess.branch_id == branch_id,
                )
                .with_for_update()
            )
            if existing is not None:
                return existing
            access = MembershipBranchAccess(
                membership_id=membership.id,
                branch_id=branch_id,
                assigned_at=now,
                assigned_by_user_id=context.user.id,
            )
            session.add(access)
            await session.flush()
            await self._increment_user_versions(session, {membership.user_id})
            self._stage_branch_event(session, context, membership, "added", branch_id)
        return access

    async def remove_branch_access(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        membership_id: UUID,
        branch_id: UUID,
    ) -> bool:
        async with session.begin():
            await self._lock_company(session, context)
            membership = await self._membership_for_update(
                session, context.company.id, membership_id
            )
            access = await session.scalar(
                select(MembershipBranchAccess)
                .where(
                    MembershipBranchAccess.membership_id == membership.id,
                    MembershipBranchAccess.branch_id == branch_id,
                )
                .with_for_update()
            )
            if access is None:
                return False
            await session.delete(access)
            await self._increment_user_versions(session, {membership.user_id})
            self._stage_branch_event(session, context, membership, "removed", branch_id)
        return True

    async def set_all_branch_access(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        membership_id: UUID,
        enabled: bool,
    ) -> Membership:
        async with session.begin():
            await self._lock_company(session, context)
            membership = await self._membership_for_update(
                session, context.company.id, membership_id
            )
            if membership.has_all_branch_access == enabled:
                return membership
            membership.has_all_branch_access = enabled
            membership.updated_at = utc_now()
            await self._increment_user_versions(session, {membership.user_id})
            self._stage_branch_event(
                session, context, membership, "all_branch_access", None
            )
        return membership

    async def list_roles(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
    ) -> list[Role]:
        return list(
            (
                await session.scalars(
                    select(Role)
                    .where(Role.company_id == context.company.id)
                    .order_by(Role.code, Role.id)
                )
            ).all()
        )

    async def create_role(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        code: str,
        name: str,
        description: str | None = None,
        is_system: bool = False,
    ) -> Role:
        normalized_code = code.strip().upper()
        if not normalized_code or not name.strip():
            raise AccessPolicyConflictError("Role code and name are required.")
        async with session.begin():
            await self._lock_company(session, context)
            existing = await session.scalar(
                select(Role)
                .where(
                    Role.company_id == context.company.id,
                    Role.code == normalized_code,
                    Role.archived_at.is_(None),
                )
                .with_for_update()
            )
            if existing is not None:
                if (
                    existing.name == name.strip()
                    and existing.description == description
                ):
                    return existing
                raise AccessPolicyConflictError("Role already exists.")
            role = Role(
                company_id=context.company.id,
                code=normalized_code,
                name=name.strip(),
                description=description,
                status="active",
                is_system=is_system,
                created_by_user_id=context.user.id,
                updated_by_user_id=context.user.id,
            )
            session.add(role)
            await session.flush()
            self._stage_event(
                session,
                context=context,
                event_type=EventType.ROLE_CREATED,
                entity_id=role.id,
                payload={"code": role.code},
            )
        return role

    async def set_role_status(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        role_id: UUID,
        status: str,
    ) -> Role:
        if status not in {"active", "inactive", "archived"}:
            raise AccessPolicyConflictError("Role status is invalid.")
        now = utc_now()
        async with session.begin():
            await self._lock_company(session, context)
            role = await self._role_for_update(session, context.company.id, role_id)
            if role.status == status:
                return role
            if role.status == "active" and status != "active":
                await self._guard_role_is_not_final_admin(
                    session, company_id=context.company.id, role_id=role.id
                )
            affected_user_ids = await self._affected_user_ids_for_role(
                session, context.company.id, role.id
            )
            role.status = status
            role.archived_at = now if status == "archived" else None
            role.updated_at = now
            role.updated_by_user_id = context.user.id
            await self._increment_user_versions(session, affected_user_ids)
            self._stage_event(
                session,
                context=context,
                event_type=EventType.ROLE_STATUS_CHANGED,
                entity_id=role.id,
                payload={"status": status},
            )
        return role

    async def assign_role(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        membership_id: UUID,
        role_id: UUID,
    ) -> MembershipRole:
        now = utc_now()
        async with session.begin():
            await self._lock_company(session, context)
            membership = await self._membership_for_update(
                session, context.company.id, membership_id
            )
            if membership.status != "active":
                raise AccessPolicyConflictError("Membership is not active.")
            role = await self._role_for_update(session, context.company.id, role_id)
            if role.status != "active" or role.archived_at is not None:
                raise AccessPolicyConflictError("Role is not active.")
            existing = await session.scalar(
                select(MembershipRole)
                .where(
                    MembershipRole.membership_id == membership.id,
                    MembershipRole.role_id == role.id,
                    MembershipRole.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if existing is not None:
                return existing
            assignment = MembershipRole(
                company_id=context.company.id,
                membership_id=membership.id,
                role_id=role.id,
                assigned_at=now,
                assigned_by_user_id=context.user.id,
            )
            session.add(assignment)
            await session.flush()
            await self._increment_user_versions(session, {membership.user_id})
            self._stage_role_assignment_event(
                session, context, membership, role, EventType.ROLE_ASSIGNED
            )
        return assignment

    async def revoke_role(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        membership_id: UUID,
        role_id: UUID,
    ) -> bool:
        now = utc_now()
        async with session.begin():
            await self._lock_company(session, context)
            membership = await self._membership_for_update(
                session, context.company.id, membership_id
            )
            role = await self._role_for_update(session, context.company.id, role_id)
            assignment = await session.scalar(
                select(MembershipRole)
                .where(
                    MembershipRole.membership_id == membership.id,
                    MembershipRole.role_id == role.id,
                    MembershipRole.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if assignment is None:
                return False
            if await self._role_has_admin_permission(session, role.id):
                await self._guard_membership_is_not_final_admin(
                    session,
                    company_id=context.company.id,
                    membership_id=membership.id,
                )
            assignment.revoked_at = now
            await self._increment_user_versions(session, {membership.user_id})
            self._stage_role_assignment_event(
                session, context, membership, role, EventType.ROLE_REVOKED
            )
        return True

    async def assign_permission(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        role_id: UUID,
        permission_id: UUID,
    ) -> RolePermission:
        async with session.begin():
            await self._lock_company(session, context)
            role = await self._role_for_update(session, context.company.id, role_id)
            if role.status != "active" or role.archived_at is not None:
                raise AccessPolicyConflictError("Role is not active.")
            permission = await session.scalar(
                select(Permission)
                .where(
                    Permission.id == permission_id,
                    Permission.status == "active",
                    Permission.retired_at.is_(None),
                )
                .with_for_update()
            )
            if permission is None:
                raise AccessPolicyNotFoundError("Permission was not found.")
            existing = await session.scalar(
                select(RolePermission)
                .where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                )
                .with_for_update()
            )
            if existing is not None:
                return existing
            assignment = RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                assigned_by_user_id=context.user.id,
            )
            session.add(assignment)
            await session.flush()
            affected = await self._affected_user_ids_for_role(
                session, context.company.id, role.id
            )
            await self._increment_user_versions(session, affected)
            self._stage_permission_event(session, context, role, permission, "added")
        return assignment

    async def remove_permission(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        role_id: UUID,
        permission_id: UUID,
    ) -> bool:
        async with session.begin():
            await self._lock_company(session, context)
            role = await self._role_for_update(session, context.company.id, role_id)
            assignment = await session.scalar(
                select(RolePermission)
                .where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission_id,
                )
                .with_for_update()
            )
            if assignment is None:
                return False
            permission = await session.get(Permission, permission_id)
            if permission is None:
                raise AccessPolicyNotFoundError("Permission was not found.")
            if permission.code == AdministrationPermission.COMPANY_ADMINISTER:
                await self._guard_role_is_not_final_admin(
                    session, company_id=context.company.id, role_id=role.id
                )
            affected = await self._affected_user_ids_for_role(
                session, context.company.id, role.id
            )
            await session.delete(assignment)
            await self._increment_user_versions(session, affected)
            self._stage_permission_event(session, context, role, permission, "removed")
        return True

    async def _lock_company(
        self, session: AsyncSession, context: AuthorizationContext
    ) -> Company:
        company = await session.scalar(
            select(Company)
            .where(
                Company.id == context.company.id,
                Company.status == "active",
                Company.archived_at.is_(None),
            )
            .with_for_update()
        )
        if company is None:
            raise AccessPolicyNotFoundError("Company was not found.")
        return company

    async def _membership_for_update(
        self, session: AsyncSession, company_id: UUID, membership_id: UUID
    ) -> Membership:
        membership = await session.scalar(
            select(Membership)
            .where(
                Membership.id == membership_id,
                Membership.company_id == company_id,
            )
            .with_for_update()
        )
        if membership is None:
            raise AccessPolicyNotFoundError("Membership was not found.")
        return membership

    async def _role_for_update(
        self, session: AsyncSession, company_id: UUID, role_id: UUID
    ) -> Role:
        role = await session.scalar(
            select(Role)
            .where(Role.id == role_id, Role.company_id == company_id)
            .with_for_update()
        )
        if role is None:
            raise AccessPolicyNotFoundError("Role was not found.")
        return role

    async def _require_active_branch(
        self, session: AsyncSession, *, company_id: UUID, branch_id: UUID
    ) -> Branch:
        branch = await session.scalar(
            select(Branch)
            .where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.status == "active",
                Branch.archived_at.is_(None),
            )
            .with_for_update()
        )
        if branch is None:
            raise AccessPolicyNotFoundError("Branch was not found.")
        return branch

    async def _increment_user_versions(
        self, session: AsyncSession, user_ids: set[UUID]
    ) -> None:
        if not user_ids:
            return
        users = list(
            (
                await session.scalars(
                    select(User).where(User.id.in_(user_ids)).with_for_update()
                )
            ).all()
        )
        if len(users) != len(user_ids):
            raise AccessPolicyConflictError("Affected User set is inconsistent.")
        for user in users:
            user.authorization_version += 1

    async def _affected_user_ids_for_role(
        self, session: AsyncSession, company_id: UUID, role_id: UUID
    ) -> set[UUID]:
        return set(
            (
                await session.scalars(
                    select(distinct(Membership.user_id))
                    .join(
                        MembershipRole,
                        MembershipRole.membership_id == Membership.id,
                    )
                    .where(
                        Membership.company_id == company_id,
                        Membership.status == "active",
                        MembershipRole.company_id == company_id,
                        MembershipRole.role_id == role_id,
                        MembershipRole.revoked_at.is_(None),
                    )
                )
            ).all()
        )

    async def _active_admin_membership_ids(
        self,
        session: AsyncSession,
        company_id: UUID,
        *,
        excluded_role_id: UUID | None = None,
    ) -> set[UUID]:
        statement = (
            select(distinct(Membership.id))
            .join(MembershipRole, MembershipRole.membership_id == Membership.id)
            .join(Role, Role.id == MembershipRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.company_id == company_id,
                Membership.status == "active",
                MembershipRole.company_id == company_id,
                MembershipRole.revoked_at.is_(None),
                Role.company_id == company_id,
                Role.status == "active",
                Role.archived_at.is_(None),
                Permission.code == AdministrationPermission.COMPANY_ADMINISTER,
                Permission.status == "active",
                Permission.retired_at.is_(None),
                User.status == "active",
                User.archived_at.is_(None),
            )
        )
        if excluded_role_id is not None:
            statement = statement.where(Role.id != excluded_role_id)
        return set((await session.scalars(statement)).all())

    async def _guard_membership_is_not_final_admin(
        self, session: AsyncSession, *, company_id: UUID, membership_id: UUID
    ) -> None:
        admin_ids = await self._active_admin_membership_ids(session, company_id)
        if membership_id in admin_ids and len(admin_ids) == 1:
            raise FinalAdministratorError(
                "The final active company administrator cannot be removed."
            )

    async def _guard_role_is_not_final_admin(
        self, session: AsyncSession, *, company_id: UUID, role_id: UUID
    ) -> None:
        current_admins = await self._active_admin_membership_ids(session, company_id)
        if not current_admins:
            return
        remaining_admins = await self._active_admin_membership_ids(
            session, company_id, excluded_role_id=role_id
        )
        if not remaining_admins:
            raise FinalAdministratorError(
                "The final active company administrator cannot be removed."
            )

    async def _role_has_admin_permission(
        self, session: AsyncSession, role_id: UUID
    ) -> bool:
        return (
            await session.scalar(
                select(RolePermission.id)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .where(
                    RolePermission.role_id == role_id,
                    Permission.code == AdministrationPermission.COMPANY_ADMINISTER,
                    Permission.status == "active",
                )
                .limit(1)
            )
        ) is not None

    def _stage_event(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        entity_id: UUID,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="access_policy",
                entity_id=entity_id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=payload,
            ),
        )
        audit_action = {
            EventType.MEMBERSHIP_CREATED: "company.membership_created",
            EventType.MEMBERSHIP_ACTIVATED: "company.membership_activated",
            EventType.MEMBERSHIP_SUSPENDED: "company.membership_suspended",
            EventType.MEMBERSHIP_REVOKED: "company.membership_revoked",
            EventType.BRANCH_ACCESS_CHANGED: "company.branch_access_changed",
            EventType.ROLE_CREATED: "company.role_created",
            EventType.ROLE_STATUS_CHANGED: "company.role_status_changed",
            EventType.ROLE_ASSIGNED: "company.role_assigned",
            EventType.ROLE_REVOKED: "company.role_revoked",
            EventType.ROLE_PERMISSIONS_CHANGED: "company.role_permissions_changed",
        }[event_type]
        audit_service.stage(
            session,
            AuditEntry(
                action=audit_action,
                resource_type="access_policy",
                resource_id=entity_id,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                details=payload,
            ),
        )

    def _stage_branch_event(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        membership: Membership,
        operation: str,
        branch_id: UUID | None,
    ) -> None:
        self._stage_event(
            session,
            context=context,
            event_type=EventType.BRANCH_ACCESS_CHANGED,
            entity_id=membership.id,
            payload={
                "operation": operation,
                "branch_id": str(branch_id) if branch_id is not None else None,
            },
        )

    def _stage_role_assignment_event(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        membership: Membership,
        role: Role,
        event_type: EventType,
    ) -> None:
        self._stage_event(
            session,
            context=context,
            event_type=event_type,
            entity_id=membership.id,
            payload={"role_id": str(role.id)},
        )

    def _stage_permission_event(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        role: Role,
        permission: Permission,
        operation: str,
    ) -> None:
        self._stage_event(
            session,
            context=context,
            event_type=EventType.ROLE_PERMISSIONS_CHANGED,
            entity_id=role.id,
            payload={
                "operation": operation,
                "permission_id": str(permission.id),
            },
        )


company_administration_service = CompanyAdministrationService()
