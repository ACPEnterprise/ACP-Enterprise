from __future__ import annotations

from ...domain import Domain, ProviderKey
from ..base import ReadOnlySkeletonAdapter
from ..contract import CapabilityState, ProviderCapability

ACCOUNTING_SCOPE = "com.intuit.quickbooks.accounting"
PAYROLL_COMPENSATION_SCOPE = "payroll.compensation.read"
EMPLOYEE_SCOPE = "qb.employee.read"
BENEFITS_SCOPE = "qb.payroll.benefits"


class QuickBooksAdapter(ReadOnlySkeletonAdapter):
    """Migration plugin boundary around the existing read-only QBO transport."""

    provider = ProviderKey("quickbooks")
    capabilities = (
        ProviderCapability(
            Domain.GL,
            CapabilityState.AVAILABLE_API,
            "QBO Accounting REST API",
            (ACCOUNTING_SCOPE,),
        ),
        ProviderCapability(
            Domain.PAYROLL,
            CapabilityState.REQUIRES_UPGRADE,
            "Payroll_EmployeeCompensation GraphQL",
            (PAYROLL_COMPENSATION_SCOPE,),
            "Silver or higher; production only",
        ),
        ProviderCapability(
            Domain.EMPLOYEES,
            CapabilityState.REQUIRES_APPROVAL,
            "WorkerManagement_Employee GraphQL",
            (EMPLOYEE_SCOPE,),
            "approved partners; production only",
        ),
        ProviderCapability(
            Domain.DEDUCTIONS_BENEFITS,
            CapabilityState.REQUIRES_APPROVAL,
            "Payroll benefits GraphQL",
            (BENEFITS_SCOPE,),
            "approved partners; production only",
        ),
        ProviderCapability(
            Domain.YTD_PAYROLL_STATE,
            CapabilityState.AVAILABLE_REPORT,
            "owner payroll report export",
            (),
            "no complete public API contract confirmed",
        ),
    )


def all_county_current_assessment() -> dict[str, object]:
    """Repository-proven access only; does not probe QBO or reveal Payroll."""
    return {
        "oauth_scopes": (ACCOUNTING_SCOPE,),
        "accounting": "AVAILABLE",
        "payroll_compensation": "ADDITIONAL SCOPE REQUIRED",
        "employee_workforce": "PARTNER APPROVAL REQUIRED",
        "benefits_deductions": "PARTNER APPROVAL REQUIRED",
        "sensitive_payroll": "ADDITIONAL AGREEMENT REQUIRED",
        "time": "ACCOUNTING TIMEACTIVITY ONLY",
        "answer_key_opened": False,
        "source_writes": False,
    }
