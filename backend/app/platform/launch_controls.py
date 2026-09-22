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
    AssetPermission,
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
    LuminaryPermission,
    PaymentPermission,
    PriceBookPermission,
    PurchasingPermission,
    SchedulingPermission,
    ServiceAgreementPermission,
    WorkforcePermission,
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
        LuminaryPermission.READ,
        BeaconPermission.REVIEW,
        CustomerPermission.READ,
        SchedulingPermission.READ,
        JobPermission.READ,
        DispatchPermission.READ,
        WorkforcePermission.CAPABILITY_MANAGE,
        WorkforcePermission.AVAILABILITY_MANAGE,
        WorkforcePermission.READ,
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
        PayrollPermission.CUTOVER_READ,
        PayrollPermission.CUTOVER_OWNER_CERTIFY,
        PayrollPermission.CUTOVER_APPROVE,
        TimekeepingPermission.ADMIN_READ,
    }
)

# Canonical Company OWNER authority is role-based, not a collection of
# person-specific grants.  This set deliberately contains normal operating and
# administrative authority while excluding the explicit execution boundaries
# that move money, post journals, execute Payroll payments, or remit taxes.
# New normal administrative capabilities are added here and inherited by every
# canonical OWNER; hard boundaries stay explicit and step-up governed.
PLATFORM_OWNER_ADMIN_PERMISSIONS = frozenset().union(
    AdministrationPermission.ALL,
    {
        LaunchPlatformPermission.AUDIT_READ,
        AnalyticsPermission.READ,
    },
    CustomerPermission.ALL,
    ServiceAgreementPermission.ALL,
    SchedulingPermission.ALL,
    JobPermission.ALL,
    DispatchPermission.ALL,
    WorkforcePermission.ALL,
    InventoryPermission.ALL,
    AssetPermission.ALL,
    PurchasingPermission.ALL,
    EconomicsPolicyPermission.ALL,
    PriceBookPermission.ALL,
    CommunicationsPermission.ALL,
    EstimatePermission.ALL,
    {
        InvoicePermission.READ,
        InvoicePermission.MANAGE,
        InvoicePermission.ISSUE,
        InvoicePermission.ADJUST,
        PaymentPermission.READ,
        AccountsPayablePermission.READ,
        AccountsPayablePermission.VENDOR_MANAGE,
        AccountsPayablePermission.BILL_PREPARE,
        AccountsPayablePermission.BILL_APPROVE,
        AccountsPayablePermission.CREDIT_MANAGE,
        AccountsPayablePermission.REPORT_READ,
        AccountsPayablePermission.MATCH_REVIEW,
        AccountingPermission.READ,
        AccountingPermission.JOURNAL_PREPARE,
        AccountingPermission.PERIOD_MANAGE,
        AccountingPermission.RECONCILE,
        AccountingPermission.FINANCE_APPROVE,
        AccountingPermission.OPENING_STATE_APPROVE,
        AccountingPermission.REPORT_READ,
        LuminaryPermission.READ,
        LuminaryPermission.ANALYZE,
        BeaconPermission.REVIEW,
        BeaconPermission.OWN,
        BeaconPermission.ASSIGN,
    },
    TimekeepingPermission.ALL,
    set(PayrollPermission.ALL)
    - {
        PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE,
        PayrollPermission.REMITTANCE_EXECUTE,
    },
)

PLATFORM_ADMIN_NORMAL_PERMISSIONS = PLATFORM_OWNER_ADMIN_PERMISSIONS - {
    PayrollPermission.CUTOVER_OWNER_CERTIFY,
    PayrollPermission.CUTOVER_APPROVE,
    PriceBookPermission.ACTIVATE,
    AccountingPermission.FINANCE_APPROVE,
    AccountingPermission.OPENING_STATE_APPROVE,
}

OFFICE_MANAGER_OPERATIONAL_PERMISSIONS = frozenset(
    {
        AdministrationPermission.MEMBERSHIP_READ,
        AdministrationPermission.MEMBERSHIP_MANAGE,
        AdministrationPermission.BRANCH_ACCESS_MANAGE,
        AdministrationPermission.ROLE_READ,
        AdministrationPermission.IDENTITY_ONBOARDING_MANAGE,
        LaunchPlatformPermission.AUDIT_READ,
        AnalyticsPermission.READ,
        CustomerPermission.READ,
        CustomerPermission.MANAGE,
        SchedulingPermission.READ,
        SchedulingPermission.MANAGE,
        JobPermission.READ,
        JobPermission.MANAGE,
        DispatchPermission.READ,
        DispatchPermission.MANAGE,
        WorkforcePermission.READ,
        WorkforcePermission.MANAGE,
        WorkforcePermission.CAPABILITY_MANAGE,
        WorkforcePermission.AVAILABILITY_MANAGE,
        PriceBookPermission.READ,
        PriceBookPermission.MANAGE,
        CommunicationsPermission.READ,
        CommunicationsPermission.MANAGE,
        EstimatePermission.READ,
        EstimatePermission.MANAGE,
        InvoicePermission.READ,
        InvoicePermission.MANAGE,
        InvoicePermission.ISSUE,
        PaymentPermission.READ,
        InventoryPermission.READ,
        InventoryPermission.MANAGE,
        InventoryPermission.MOVE,
        InventoryPermission.RESERVE,
        PurchasingPermission.READ,
        PurchasingPermission.MANAGE,
        TimekeepingPermission.ADMIN_READ,
    }
)


class LaunchRoleCode(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    CSR = "CSR"
    COMPANY_ADMINISTRATOR = "COMPANY_ADMINISTRATOR"
    OFFICE_MANAGER = "OFFICE_MANAGER"
    DISPATCHER = "DISPATCHER"
    TECHNICIAN = "TECHNICIAN"
    AUDITOR = "AUDITOR"
    SUPPORT = "SUPPORT"
    SERVICE_CSR = "SERVICE_CSR"
    OWN_DATA_ROLE = "OWN_DATA_ROLE"
    ACP_EMPLOYEE_MOBILE = "ACP_EMPLOYEE_MOBILE"


@dataclass(frozen=True, slots=True)
class LaunchRoleDefinition:
    code: LaunchRoleCode
    purpose: str
    permission_codes: frozenset[str]
    branch_access_required: bool = True
    tenant_impersonation_allowed: bool = False


LAUNCH_ROLE_MATRIX = (
    LaunchRoleDefinition(
        code=LaunchRoleCode.OWNER,
        purpose="Own the Company and administer its access and operating evidence.",
        permission_codes=PLATFORM_OWNER_ADMIN_PERMISSIONS,
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.ADMIN,
        purpose=(
            "Administer normal Company access and operations without canonical-owner "
            "decisions, money movement, journal posting, or Payroll payment execution."
        ),
        permission_codes=PLATFORM_ADMIN_NORMAL_PERMISSIONS,
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.MANAGER,
        purpose="Manage branch operations using the canonical office-manager bundle.",
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
        code=LaunchRoleCode.CSR,
        purpose="Serve Customers without financial execution or administrative authority.",
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
        code=LaunchRoleCode.COMPANY_ADMINISTRATOR,
        purpose="Company-owned tenant and access-policy administration.",
        permission_codes=COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS,
    ),
    LaunchRoleDefinition(
        code=LaunchRoleCode.OFFICE_MANAGER,
        purpose=(
            "Operate normal Company office, workforce, Customer, scheduling, "
            "dispatch, estimate, invoice, and read-only payment workflows without "
            "owner-only activation, money movement, Payroll, or Accounting authority."
        ),
        permission_codes=OFFICE_MANAGER_OPERATIONAL_PERMISSIONS,
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
        purpose=(
            "Use ACP Employee for own-day work, Timekeeping, and assigned Job "
            "execution without office, administrative, or Payroll authority."
        ),
        permission_codes=frozenset(
            {
                CustomerPermission.READ,
                SchedulingPermission.READ,
                JobPermission.READ,
                JobPermission.EXECUTE,
                EmployeeOperationsPermission.OWN_DAY_READ,
                TimekeepingPermission.OWN_READ,
                TimekeepingPermission.OWN_PUNCH,
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
    LaunchRoleDefinition(
        code=LaunchRoleCode.ACP_EMPLOYEE_MOBILE,
        purpose=(
            "Use ACP Employee for own-day work, Timekeeping, and assigned Job "
            "execution without office or Payroll authority."
        ),
        permission_codes=frozenset(
            {
                EmployeeOperationsPermission.OWN_DAY_READ,
                TimekeepingPermission.OWN_PUNCH,
                TimekeepingPermission.OWN_READ,
                JobPermission.READ,
                JobPermission.EXECUTE,
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
