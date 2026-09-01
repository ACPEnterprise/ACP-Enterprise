from collections import defaultdict
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.employees.models import Employee
from app.platform.onboarding.models import IdentityOnboardingRequest
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User
from app.workforce.schemas import (
    EmployeeAdministrationDetail,
    EmployeeAdministrationSummary,
    EmployeePermissionExplanation,
    WorkforceEmployeeDetail,
)
from app.workforce.service import workforce_operations_service


def _business_area(code: str) -> str:
    prefixes = (
        ("COMPANY_CUSTOMER_", "Customers"),
        ("COMPANY_ESTIMATE_", "Estimates"),
        ("COMPANY_SCHEDULING_", "Scheduling"),
        ("COMPANY_JOB_", "Jobs"),
        ("COMPANY_DISPATCH_", "Dispatch"),
        ("COMPANY_INVOICE_", "Invoices"),
        ("COMPANY_PAYMENT_", "Payments"),
        ("COMPANY_COMMUNICATION", "Communications"),
        ("COMPANY_SERVICE_AGREEMENT_", "Service Agreements"),
        ("COMPANY_PURCHASING_", "Purchasing"),
        ("COMPANY_INVENTORY_", "Inventory"),
        ("COMPANY_WORKFORCE_", "Workforce"),
        ("COMPANY_TIMEKEEPING_", "Timekeeping"),
        ("COMPANY_PAYROLL_", "Payroll"),
        ("COMPANY_ACCOUNTING_", "Accounting"),
        ("COMPANY_BEACON_", "Beacon"),
        ("COMPANY_MIGRATION_", "Migration"),
        ("COMPANY_AUDIT_", "Audit"),
        ("COMPANY_", "Administration"),
    )
    return next((name for prefix, name in prefixes if code.startswith(prefix)), "Other")


class EmployeeAdministrationService:
    async def detail(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
    ) -> EmployeeAdministrationDetail | None:
        workforce = await workforce_operations_service.detail(
            session, context=context, employee_id=employee_id
        )
        if workforce is None:
            return None
        summary = await self._summary(
            session,
            context=context,
            employee_id=employee_id,
            workforce=workforce,
        )
        role_ids = tuple(
            await session.scalars(
                select(MembershipRole.role_id).where(
                    MembershipRole.company_id == context.company.id,
                    MembershipRole.membership_id == summary.membership_id,
                    MembershipRole.revoked_at.is_(None),
                )
            )
        )
        rows = (
            await session.execute(
                select(Permission, Role.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(Role, Role.id == RolePermission.role_id)
                .where(
                    Role.company_id == context.company.id,
                    Role.id.in_(role_ids),
                    Role.status == "active",
                    Permission.status == "active",
                )
                .order_by(Permission.code, Role.code)
            )
        ).all()
        role_codes_by_permission: dict[str, list[str]] = defaultdict(list)
        permission_by_code: dict[str, Permission] = {}
        for permission, role_code in rows:
            permission_by_code[permission.code] = permission
            role_codes_by_permission[permission.code].append(role_code)
        definitions = {
            definition.code: definition for definition in permission_catalog.definitions
        }
        explanations = tuple(
            EmployeePermissionExplanation(
                code=code,
                name=(
                    definitions[code].name
                    if code in definitions
                    else permission_by_code[code].name
                ),
                business_area=_business_area(code),
                authority=(
                    "OWN_DATA_ONLY"
                    if "_OWN_" in code or code.endswith("_OWN_READ")
                    else "ROLE_DERIVED"
                ),
                role_codes=tuple(sorted(set(role_codes))),
                branch_scoped=summary.branch_ids != (),
            )
            for code, role_codes in sorted(role_codes_by_permission.items())
        )
        return EmployeeAdministrationDetail(
            **summary.model_dump(), permissions=explanations, workforce=workforce
        )

    async def _summary(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        workforce: WorkforceEmployeeDetail,
    ) -> EmployeeAdministrationSummary:
        row = (
            await session.execute(
                select(Employee, Membership, User)
                .outerjoin(
                    Membership,
                    (Membership.company_id == Employee.company_id)
                    & (Membership.id == Employee.membership_id),
                )
                .outerjoin(User, User.id == Membership.user_id)
                .where(
                    Employee.company_id == context.company.id,
                    Employee.id == employee_id,
                )
            )
        ).one()
        _employee, membership, user = row
        branch_ids: tuple[UUID, ...] = ()
        role_codes: tuple[str, ...] = ()
        if membership is not None:
            branch_ids = tuple(
                await session.scalars(
                    select(MembershipBranchAccess.branch_id)
                    .where(MembershipBranchAccess.membership_id == membership.id)
                    .order_by(MembershipBranchAccess.branch_id)
                )
            )
            role_codes = tuple(
                await session.scalars(
                    select(Role.code)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(
                        MembershipRole.company_id == context.company.id,
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.revoked_at.is_(None),
                        Role.company_id == context.company.id,
                    )
                    .order_by(Role.code)
                )
            )
        onboarding = await session.scalar(
            select(IdentityOnboardingRequest)
            .where(
                IdentityOnboardingRequest.company_id == context.company.id,
                IdentityOnboardingRequest.employee_id == employee_id,
            )
            .order_by(IdentityOnboardingRequest.created_at.desc())
        )
        mobile_blockers: list[str] = []
        if membership is None:
            mobile_blockers.append("membership_missing")
        elif membership.status != "active":
            mobile_blockers.append("membership_inactive")
        if user is None:
            mobile_blockers.append("user_missing")
        elif user.status != "active" or user.archived_at is not None:
            mobile_blockers.append("user_inactive")
        if not branch_ids and not (membership and membership.has_all_branch_access):
            mobile_blockers.append("branch_grant_missing")
        if not any(code in {"TECHNICIAN", "OWN_DATA_ROLE", "COMPANY_USER"} for code in role_codes):
            mobile_blockers.append("mobile_role_missing")
        mobile_state: Literal["READY", "BLOCKED", "NOT_LINKED"] = (
            "NOT_LINKED"
            if membership is None or user is None
            else "READY" if not mobile_blockers else "BLOCKED"
        )
        return EmployeeAdministrationSummary(
            **workforce.model_dump(
                exclude={
                    "capabilities",
                    "certifications",
                    "languages",
                    "branches",
                    "work_restrictions",
                    "equipment_capabilities",
                    "availability",
                }
            ),
            membership_id=membership.id if membership else None,
            membership_status=membership.status if membership else None,
            user_status=user.status if user else None,
            authorization_version=user.authorization_version if user else None,
            branch_ids=branch_ids,
            role_codes=role_codes,
            onboarding_status=onboarding.status if onboarding else None,
            masked_login=onboarding.masked_login if onboarding else None,
            mobile_readiness=mobile_state,
            mobile_readiness_blockers=tuple(mobile_blockers),
        )


employee_administration_service = EmployeeAdministrationService()
