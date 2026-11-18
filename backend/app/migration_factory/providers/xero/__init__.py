from ...domain import Domain, ProviderKey
from ..base import ReadOnlySkeletonAdapter
from ..contract import CapabilityState, ProviderCapability


class XeroAdapter(ReadOnlySkeletonAdapter):
    provider = ProviderKey("xero")
    capabilities = tuple(
        ProviderCapability(domain, CapabilityState.REQUIRES_APPROVAL, resource)
        for domain, resource in (
            (Domain.COMPANY, "organisation"),
            (Domain.CUSTOMERS, "contacts"),
            (Domain.VENDORS, "contacts"),
            (Domain.CHART_OF_ACCOUNTS, "accounts"),
            (Domain.INVOICES, "invoices"),
            (Domain.PAYMENTS, "payments"),
            (Domain.BANKING, "bank transactions"),
            (Domain.GL, "journals/reports"),
            (Domain.PAYROLL, "regional payroll API or file fallback"),
        )
    )
