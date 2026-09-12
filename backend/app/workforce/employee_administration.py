from collections import defaultdict
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.employees.models import Employee
from app.platform.notifications.models import NotificationOutbox
from app.platform.onboarding.models import (
    IdentityOnboardingInvitation,
    IdentityOnboardingRequest,
)
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

MOBILE_REQUIRED_PERMISSION_CODES = frozenset(
    {
        "COMPANY_TIMEKEEPING_OWN_READ",
        "COMPANY_TIMEKEEPING_OWN_PUNCH",
        "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ",
        "COMPANY_JOB_READ",
        "COMPANY_JOB_EXECUTE",
    }
)


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
    @staticmethod
    def _access_and_mobile_readiness(
        *,
        employee_status: str,
        membership_status: str | None,
        user_status: str | None,
        has_branch_access: bool,
        effective_permission_codes: frozenset[str],
    ) -> tuple[
        Literal["ACTIVE", "DISABLED", "INVITED", "NOT_LINKED"],
        Literal["READY", "BLOCKED", "NOT_LINKED"],
        tuple[str, ...],
    ]:
        blockers: list[str] = []
        if membership_status is None or user_status is None:
            access_status: Literal[
                "ACTIVE", "DISABLED", "INVITED", "NOT_LINKED"
            ] = "NOT_LINKED"
        elif membership_status == "invited" or user_status == "invited":
            access_status = "INVITED"
        elif (
            employee_status == "active"
            and membership_status == "active"
            and user_status == "active"
        ):
            access_status = "ACTIVE"
        else:
            access_status = "DISABLED"
        if membership_status is None:
            blockers.append("membership_missing")
        elif membership_status != "active":
            blockers.append("membership_inactive")
        if user_status is None:
            blockers.append("user_missing")
        elif user_status != "active":
            blockers.append("user_inactive")
        if employee_status != "active":
            blockers.append("employee_inactive")
        if not has_branch_access:
            blockers.append("branch_grant_missing")
        if not MOBILE_REQUIRED_PERMISSION_CODES.issubset(
            effective_permission_codes
        ):
            blockers.append("mobile_permissions_missing")
        mobile_state: Literal["READY", "BLOCKED", "NOT_LINKED"] = (
            "NOT_LINKED"
            if membership_status is None or user_status is None
            else "READY" if not blockers else "BLOCKED"
        )
        return access_status, mobile_state, tuple(blockers)

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
        effective_permission_codes: frozenset[str] = frozenset()
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
            effective_permission_codes = frozenset(
                await session.scalars(
                    select(Permission.code)
                    .select_from(MembershipRole)
                    .join(Role, Role.id == MembershipRole.role_id)
                    .join(RolePermission, RolePermission.role_id == Role.id)
                    .join(Permission, Permission.id == RolePermission.permission_id)
                    .where(
                        MembershipRole.company_id == context.company.id,
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.revoked_at.is_(None),
                        Role.company_id == context.company.id,
                        Role.status == "active",
                        Permission.status == "active",
                    )
                )
            )
        onboarding = await session.scalar(
            select(IdentityOnboardingRequest)
            .where(
                IdentityOnboardingRequest.company_id == context.company.id,
                IdentityOnboardingRequest.employee_id == employee_id,
            )
            .order_by(IdentityOnboardingRequest.created_at.desc())
            .limit(1)
        )
        invitation = (
            await session.scalar(
                select(IdentityOnboardingInvitation)
                .where(
                    IdentityOnboardingInvitation.onboarding_request_id
                    == onboarding.id
                )
                .order_by(IdentityOnboardingInvitation.created_at.desc())
                .limit(1)
            )
            if onboarding is not None
            else None
        )
        delivery = (
            await session.scalar(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.company_id == context.company.id,
                    NotificationOutbox.branch_id == onboarding.branch_id,
                    NotificationOutbox.recipient_reference
                    == f"invitation:{invitation.id}",
                    NotificationOutbox.notification_type
                    == "identity.onboarding_invitation",
                    NotificationOutbox.channel == "email",
                    NotificationOutbox.recipient == user.normalized_email,
                )
                .order_by(NotificationOutbox.created_at.desc())
                .limit(1)
            )
            if onboarding is not None and invitation is not None and user is not None
            else None
        )
        delivery_status = (
            "delivered"
            if delivery is not None and delivery.status == "sent"
            else "uncertain"
            if delivery is not None and delivery.status == "ambiguous"
            else delivery.status
            if delivery is not None
            else None
        )
        access_status, mobile_state, mobile_blockers = (
            self._access_and_mobile_readiness(
                employee_status=workforce.employee_status,
                membership_status=membership.status if membership else None,
                user_status=(
                    user.status
                    if user is not None and user.archived_at is None
                    else "archived"
                    if user is not None
                    else None
                ),
                has_branch_access=bool(
                    branch_ids or (membership and membership.has_all_branch_access)
                ),
                effective_permission_codes=effective_permission_codes,
            )
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
            invitation_status=invitation.status if invitation else None,
            delivery_status=delivery_status,
            login_email=user.normalized_email if user else None,
            masked_login=onboarding.masked_login if onboarding else None,
            access_status=access_status,
            mobile_readiness=mobile_state,
            mobile_readiness_blockers=mobile_blockers,
        )


employee_administration_service = EmployeeAdministrationService()
