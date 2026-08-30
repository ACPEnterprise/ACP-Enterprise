from dataclasses import dataclass
from enum import StrEnum

from app.employee_operations.permissions import EmployeeOperationsPermission
from app.payroll.permissions import PayrollPermission
from app.platform.permissions.catalog import PermissionCatalog
from app.platform.permissions.codes import (
    AccountingPermission,
    AccountsPayablePermission,
    AdministrationPermission,
    AnalyticsPermission,
    BeaconPermission,
    CommunicationsPermission,
    CustomerPermission,
    DispatchPermission,
    EconomicsPolicyPermission,
    EstimatePermission,
    InventoryPermission,
    InvoicePermission,
    JobPermission,
    LaunchPlatformPermission,
    PaymentPermission,
    PriceBookPermission,
    PurchasingPermission,
    SchedulingPermission,
)
from app.timekeeping.permissions import TimekeepingPermission

COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS = frozenset(
    {
        AdministrationPermission.MEMBERSHIP_READ,
        AdministrationPermission.MEMBERSHIP_MANAGE,
        AdministrationPermission.BRANCH_ACCESS_MANAGE,
        AdministrationPermission.ROLE_READ,
        AdministrationPermission.ROLE_MANAGE,
        AdministrationPermission.PERMISSION_MANAGE,
        AdministrationPermission.COMPANY_ADMINISTER,
        AdministrationPermission.IDENTITY_ONBOARDING_MANAGE,
        LaunchPlatformPermission.AUDIT_READ,
        AnalyticsPermission.READ,
        BeaconPermission.REVIEW,
        CustomerPermission.READ,
        SchedulingPermission.READ,
        JobPermission.READ,
        DispatchPermission.READ,
        EconomicsPolicyPermission.MEASUREMENT_READ,
        InventoryPermission.READ,
        PurchasingPermission.READ,
        AccountingPermission.REPORT_READ,
        PriceBookPermission.READ,
        CommunicationsPermission.READ,
        EstimatePermission.READ,
        InvoicePermission.READ,
        PaymentPermission.READ,
        AccountsPayablePermission.REPORT_READ,
        PayrollPermission.REPORTING_READ,
    }
)


class LaunchRoleCode(StrEnum):
    COMPANY_ADMINISTRATOR = "COMPANY_ADMINISTRATOR"
    OFFICE_MANAGER = "OFFICE_MANAGER"
    DISPATCHER = "DISPATCHER"
    TECHNICIAN = "TECHNICIAN"
    AUDITOR = "AUDITOR"
    SUPPORT = "SUPPORT"
    SERVICE_CSR = "SERVICE_CSR"
    OWN_DATA_ROLE = "OWN_DATA_ROLE"


@dataclass(frozen=True, slots=True)
class LaunchRoleDefinition:
    code: LaunchRoleCode
    purpose: str
    permission_codes: frozenset[str]
    branch_access_required: bool = True
    tenant_impersonation_allowed: bool = False


LAUNCH_ROLE_MATRIX = (
    LaunchRoleDefinition(
        code=LaunchRoleCode.COMPANY_ADMINISTRATOR,
        purpose="Company-owned tenant and access-policy administration.",
        permission_codes=COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS,
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.OFFICE_MANAGER,
        purpose="Branch operations and commercial catalog administration.",
        permission_codes=frozenset(
            {
                CustomerPermission.READ,
                CustomerPermission.MANAGE,
                SchedulingPermission.READ,
                SchedulingPermission.MANAGE,
                JobPermission.READ,
                JobPermission.MANAGE,
                DispatchPermission.READ,
                DispatchPermission.MANAGE,
                PriceBookPermission.READ,
                PriceBookPermission.MANAGE,
                PriceBookPermission.ACTIVATE,
                AnalyticsPermission.READ,
                LaunchPlatformPermission.AUDIT_READ,
                InventoryPermission.READ,
                InventoryPermission.MANAGE,
                InventoryPermission.MOVE,
                InventoryPermission.RESERVE,
                PurchasingPermission.READ,
                PurchasingPermission.MANAGE,
            }
        ),
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.DISPATCHER,
        purpose="Schedule work and make explicit operational assignments.",
        permission_codes=frozenset(
            {
                CustomerPermission.READ,
                SchedulingPermission.READ,
                SchedulingPermission.MANAGE,
                JobPermission.READ,
                JobPermission.MANAGE,
                DispatchPermission.READ,
                DispatchPermission.MANAGE,
                PriceBookPermission.READ,
                InventoryPermission.READ,
                InventoryPermission.RESERVE,
            }
        ),
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.TECHNICIAN,
        purpose="Read assigned operational context and execute Job lifecycle work.",
        permission_codes=frozenset(
            {
                CustomerPermission.READ,
                SchedulingPermission.READ,
                JobPermission.READ,
                JobPermission.EXECUTE,
            }
        ),
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.AUDITOR,
        purpose="Read bounded Company audit and analytics evidence.",
        permission_codes=frozenset(
            {LaunchPlatformPermission.AUDIT_READ, AnalyticsPermission.READ}
        ),
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.SUPPORT,
        purpose="No standing tenant access; use owner-mediated evidence only.",
        permission_codes=frozenset(),
        branch_access_required=False,
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.SERVICE_CSR,
        purpose=(
            "Serve Customers and inspect branch-scoped operational and commercial "
            "status without financial execution or administrative authority."
        ),
        permission_codes=frozenset(
            {
                CustomerPermission.READ,
                CustomerPermission.MANAGE,
                EstimatePermission.READ,
                EstimatePermission.MANAGE,
                SchedulingPermission.READ,
                JobPermission.READ,
                DispatchPermission.READ,
                InvoicePermission.READ,
                PaymentPermission.READ,
                CommunicationsPermission.READ,
            }
        ),
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.OWN_DATA_ROLE,
        purpose=(
            "Access only the authenticated Employee's own operational day, "
            "Timekeeping, and Pay Statement evidence."
        ),
        permission_codes=frozenset(
            {
                EmployeeOperationsPermission.OWN_DAY_READ,
                TimekeepingPermission.OWN_PUNCH,
                TimekeepingPermission.OWN_READ,
                PayrollPermission.STATEMENT_OWN_READ,
            }
        ),
    ),
)


class LaunchRoleMatrixError(ValueError):
    pass


def validate_launch_role_matrix(catalog: PermissionCatalog) -> None:
    canonical = frozenset(item.code for item in catalog.definitions)
    seen: set[LaunchRoleCode] = set()
    for role in LAUNCH_ROLE_MATRIX:
        if role.code in seen:
            raise LaunchRoleMatrixError(f"Duplicate launch role: {role.code}")
        seen.add(role.code)
        unknown = role.permission_codes - canonical
        if unknown:
            raise LaunchRoleMatrixError(
                f"Launch role {role.code} contains unknown permissions: "
                f"{', '.join(sorted(unknown))}"
            )
        if role.tenant_impersonation_allowed:
            raise LaunchRoleMatrixError(
                f"Launch role {role.code} cannot grant tenant impersonation."
            )
