import re
from dataclasses import dataclass
from enum import StrEnum

from app.payroll.permissions import PayrollPermission
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
    EngineeringCapacityPermission,
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
    EngineeringRepositoryOperationPermission,
    EstimatePermission,
    InventoryPermission,
    InvoicePermission,
    JobPermission,
    LaunchPlatformPermission,
    PaymentPermission,
    PriceBookPermission,
    PurchasingPermission,
    SchedulingPermission,
    WorkerControlPermission,
    WorkerIdentityPermission,
)
from app.timekeeping.permissions import TimekeepingPermission

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class PermissionScope(StrEnum):
    COMPANY = "company"
    PLATFORM = "platform"


@dataclass(frozen=True)
class PermissionDefinition:
    code: str
    name: str
    resource: str
    action: str
    scope: PermissionScope
    reserved: bool = False


class PermissionCatalogError(ValueError):
    pass


class PermissionCatalog:
    def __init__(self, definitions: tuple[PermissionDefinition, ...]) -> None:
        self.definitions = definitions

    def validate(self) -> None:
        seen: set[str] = set()
        for definition in self.definitions:
            if definition.code in seen:
                raise PermissionCatalogError(
                    f"Duplicate permission code: {definition.code}"
                )
            seen.add(definition.code)
            if not CODE_PATTERN.fullmatch(definition.code):
                raise PermissionCatalogError(
                    f"Invalid permission code: {definition.code}"
                )
            if (
                not definition.name.strip()
                or not definition.resource.strip()
                or not definition.action.strip()
            ):
                raise PermissionCatalogError(
                    f"Invalid permission definition: {definition.code}"
                )
            expected_prefix = (
                "COMPANY_"
                if definition.scope is PermissionScope.COMPANY
                else "PLATFORM_"
            )
            if not definition.code.startswith(expected_prefix):
                raise PermissionCatalogError(
                    f"Permission scope does not match code: {definition.code}"
                )
        reserved = {
            definition.code: definition
            for definition in self.definitions
            if definition.reserved
        }
        for code, definition in reserved.items():
            if definition.scope is not PermissionScope.COMPANY:
                raise PermissionCatalogError(
                    f"Reserved permission has invalid scope: {code}"
                )


ADMINISTRATION_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="company_access_policy",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
        reserved=True,
    )
    for code in sorted(AdministrationPermission.ALL)
)

LAUNCH_PLATFORM_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name="Company Audit Read",
        resource="audit",
        action="read",
        scope=PermissionScope.COMPANY,
        reserved=True,
    )
    for code in sorted(LaunchPlatformPermission.ALL)
)

CUSTOMER_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="customer",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(CustomerPermission.ALL)
)

ANALYTICS_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name="Company Analytics Read",
        resource="analytics",
        action="read",
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(AnalyticsPermission.ALL)
)

BEACON_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="beacon",
        action=code.removeprefix("COMPANY_BEACON_").lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(BeaconPermission.ALL)
)

TIMEKEEPING_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="timekeeping",
        action=code.removeprefix("COMPANY_TIMEKEEPING_").lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(TimekeepingPermission.ALL)
)

PAYROLL_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="payroll_authority",
        action=code.removeprefix("COMPANY_PAYROLL_").lower(),
        scope=PermissionScope.COMPANY,
        reserved=True,
    )
    for code in sorted(PayrollPermission.ALL)
)

SCHEDULING_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="scheduling",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(SchedulingPermission.ALL)
)

JOB_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="job",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(JobPermission.ALL)
)

DISPATCH_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="dispatch",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(DispatchPermission.ALL)
)

INVENTORY_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="inventory",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(InventoryPermission.ALL)
)

PURCHASING_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="purchasing",
        action=code.removeprefix("COMPANY_PURCHASING_").lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(PurchasingPermission.ALL)
)

ACCOUNTING_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="accounting",
        action=code.removeprefix("COMPANY_ACCOUNTING_").lower(),
        scope=PermissionScope.COMPANY,
        reserved=True,
    )
    for code in sorted(AccountingPermission.ALL)
)

ECONOMICS_POLICY_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="economics_policy",
        action=code.removeprefix("COMPANY_ECONOMICS_POLICY_").lower(),
        scope=PermissionScope.COMPANY,
        reserved=True,
    )
    for code in sorted(EconomicsPolicyPermission.ALL)
)

PRICE_BOOK_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="price_book",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(PriceBookPermission.ALL)
)

COMMUNICATIONS_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="communications",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(CommunicationsPermission.ALL)
)

ESTIMATE_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="estimate",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(EstimatePermission.ALL)
)

INVOICE_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="invoice",
        action=code.removeprefix("COMPANY_INVOICE_").lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(InvoicePermission.ALL)
)

PAYMENT_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="payment",
        action=code.removeprefix("COMPANY_PAYMENT_").lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(PaymentPermission.ALL)
)

ACCOUNTS_PAYABLE_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="accounts_payable",
        action=code.removeprefix("COMPANY_ACCOUNTS_PAYABLE_").lower(),
        scope=PermissionScope.COMPANY,
        reserved=True,
    )
    for code in sorted(AccountsPayablePermission.ALL)
)

ENGINEERING_COMMAND_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="engineering_command",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(EngineeringCommandPermission.ALL)
)

ENGINEERING_EXECUTION_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="engineering_execution",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(EngineeringExecutionPermission.ALL)
)

ENGINEERING_CAPACITY_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="engineering_capacity",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(EngineeringCapacityPermission.ALL)
)

ENGINEERING_REPOSITORY_OPERATION_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="engineering_repository_operation",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(EngineeringRepositoryOperationPermission.ALL)
)

WORKER_CONTROL_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="engineering_worker",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(WorkerControlPermission.ALL)
)

WORKER_IDENTITY_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="worker_identity",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(WorkerIdentityPermission.ALL)
)

permission_catalog = PermissionCatalog(
    ADMINISTRATION_DEFINITIONS
    + LAUNCH_PLATFORM_DEFINITIONS
    + CUSTOMER_DEFINITIONS
    + ANALYTICS_DEFINITIONS
    + BEACON_DEFINITIONS
    + TIMEKEEPING_DEFINITIONS
    + PAYROLL_DEFINITIONS
    + SCHEDULING_DEFINITIONS
    + JOB_DEFINITIONS
    + DISPATCH_DEFINITIONS
    + INVENTORY_DEFINITIONS
    + PURCHASING_DEFINITIONS
    + ACCOUNTING_DEFINITIONS
    + ECONOMICS_POLICY_DEFINITIONS
    + PRICE_BOOK_DEFINITIONS
    + COMMUNICATIONS_DEFINITIONS
    + ESTIMATE_DEFINITIONS
    + INVOICE_DEFINITIONS
    + PAYMENT_DEFINITIONS
    + ACCOUNTS_PAYABLE_DEFINITIONS
    + ENGINEERING_COMMAND_DEFINITIONS
    + ENGINEERING_EXECUTION_DEFINITIONS
    + ENGINEERING_CAPACITY_DEFINITIONS
    + ENGINEERING_REPOSITORY_OPERATION_DEFINITIONS
    + WORKER_CONTROL_DEFINITIONS
    + WORKER_IDENTITY_DEFINITIONS
)
