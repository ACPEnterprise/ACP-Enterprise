from ...domain import Domain, ProviderKey
from ..base import ReadOnlySkeletonAdapter
from ..contract import CapabilityState, ProviderCapability


class SageAdapter(ReadOnlySkeletonAdapter):
    provider = ProviderKey("sage")
    capabilities = tuple(
        ProviderCapability(domain, CapabilityState.REQUIRES_APPROVAL, resource)
        for domain, resource in (
            (Domain.COMPANY, "business"),
            (Domain.CUSTOMERS, "contacts"),
            (Domain.VENDORS, "contacts"),
            (Domain.CHART_OF_ACCOUNTS, "ledger accounts"),
            (Domain.INVOICES, "sales/purchase documents"),
            (Domain.PAYMENTS, "payments"),
            (Domain.BANKING, "bank transactions"),
            (Domain.GL, "journals/reports"),
            (Domain.PAYROLL, "product/region-specific API or file fallback"),
        )
    )
