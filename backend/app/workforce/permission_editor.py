from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.service import AuditEntry, audit_service
from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.models import (
    MembershipPermissionOverride,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User
from app.workforce.schemas import EmployeePermissionUpdateRequest


class EmployeePermissionEditorConflict(ValueError):
    pass


PROFILE_ROLE_CODES: dict[str, tuple[str, ...]] = {
    "COMPANY_ADMINISTRATOR": ("COMPANY_ADMINISTRATOR", "OWNER"),
    "OFFICE_MANAGER": ("OFFICE_MANAGER",),
    "FIELD_MANAGER": ("FIELD_MANAGER",),
    "TECHNICIAN": ("TECHNICIAN",),
    "HELPER": ("HELPER",),
}


class EmployeePermissionEditorService:
    async def update(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        data: EmployeePermissionUpdateRequest,
    ) -> None:
        if data.access_profile not in {*PROFILE_ROLE_CODES, "CUSTOM"}:
            raise EmployeePermissionEditorConflict("Choose a supported Access Profile.")

        async with session.begin():
            row = (
                await session.execute(
                    select(Employee, Membership, User)
                    .join(
                        Membership,
                        (Membership.company_id == Employee.company_id)
                        & (Membership.id == Employee.membership_id),
                    )
                    .join(User, User.id == Membership.user_id)
                    .where(
                        Employee.company_id == context.company.id,
                        Employee.id == employee_id,
                        Membership.status == "active",
                        User.archived_at.is_(None),
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                raise EmployeePermissionEditorConflict(
                    "Employee access identity was not found."
                )
            _employee, membership, user = row
            if user.authorization_version != data.expected_authorization_version:
                raise EmployeePermissionEditorConflict(
                    "Employee access changed. Refresh before saving again."
                )

            requested_codes = {code.strip().upper() for code in data.permission_codes}
            permissions = tuple(
                await session.scalars(
                    select(Permission).where(
                        Permission.status == "active",
                        Permission.retired_at.is_(None),
                        Permission.code.like("COMPANY\\_%", escape="\\"),
                    )
                )
            )
            permission_by_code = {
                permission.code: permission for permission in permissions
            }
            unknown = requested_codes - permission_by_code.keys()
            if unknown:
                raise EmployeePermissionEditorConflict(
                    "One or more permissions are unavailable."
                )

            if data.access_profile != "CUSTOM":
                role_codes = PROFILE_ROLE_CODES[data.access_profile]
                roles = tuple(
                    await session.scalars(
                        select(Role).where(
                            Role.company_id == context.company.id,
                            Role.status == "active",
                            Role.archived_at.is_(None),
                            Role.code.in_(role_codes),
                        )
                    )
                )
                target_role = next(
                    (role for role in roles if role.code in role_codes), None
                )
                if target_role is None:
                    raise EmployeePermissionEditorConflict(
                        "The selected Access Profile is not configured for this Company."
                    )
                active_roles = tuple(
                    await session.scalars(
                        select(MembershipRole).where(
                            MembershipRole.company_id == context.company.id,
                            MembershipRole.membership_id == membership.id,
                            MembershipRole.revoked_at.is_(None),
                        )
                    )
                )
                now = datetime.now(timezone.utc)
                for assignment in active_roles:
                    assignment_role = await session.get(Role, assignment.role_id)
                    if (
                        assignment_role is not None
                        and assignment_role.code
                        in {
                            code
                            for codes in PROFILE_ROLE_CODES.values()
                            for code in codes
                        }
                        and assignment.role_id != target_role.id
                    ):
                        assignment.revoked_at = now
                        assignment.revoked_by_user_id = context.user.id
                        assignment.revocation_reason = "Access Profile changed"
                if not any(
                    assignment.role_id == target_role.id
                    and assignment.revoked_at is None
                    for assignment in active_roles
                ):
                    session.add(
                        MembershipRole(
                            company_id=context.company.id,
                            membership_id=membership.id,
                            role_id=target_role.id,
                            assigned_by_user_id=context.user.id,
                        )
                    )

            role_permission_codes = set(
                await session.scalars(
                    select(Permission.code)
                    .select_from(MembershipRole)
                    .join(
                        RolePermission, RolePermission.role_id == MembershipRole.role_id
                    )
                    .join(Permission, Permission.id == RolePermission.permission_id)
                    .where(
                        MembershipRole.company_id == context.company.id,
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.revoked_at.is_(None),
                        Permission.status == "active",
                        Permission.retired_at.is_(None),
                    )
                )
            )
            existing = {
                permission.permission_id: permission
                for permission in (
                    await session.scalars(
                        select(MembershipPermissionOverride).where(
                            MembershipPermissionOverride.company_id
                            == context.company.id,
                            MembershipPermissionOverride.membership_id == membership.id,
                        )
                    )
                )
            }
            for permission in permissions:
                desired = permission.code in requested_codes
                baseline = permission.code in role_permission_codes
                override = existing.get(permission.id)
                if desired == baseline:
                    if override is not None:
                        await session.delete(override)
                    continue
                if override is None:
                    session.add(
                        MembershipPermissionOverride(
                            company_id=context.company.id,
                            membership_id=membership.id,
                            permission_id=permission.id,
                            effect="grant" if desired else "deny",
                            assigned_by_user_id=context.user.id,
                        )
                    )
                else:
                    override.effect = "grant" if desired else "deny"
                    override.assigned_by_user_id = context.user.id

            user.authorization_version += 1
            audit_service.stage(
                session,
                AuditEntry(
                    action="workforce.employee_permissions_updated",
                    resource_type="employee",
                    resource_id=employee_id,
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=context.active_branch.id
                    if context.active_branch
                    else None,
                    reason_code="employee_access_editor",
                    details={
                        "access_profile": data.access_profile,
                        "permission_count": len(requested_codes),
                        "authorization_version": user.authorization_version,
                    },
                    occurred_at=datetime.now(timezone.utc),
                ),
            )


employee_permission_editor_service = EmployeePermissionEditorService()
