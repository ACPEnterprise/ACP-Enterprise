from ...domain import Domain, ProviderKey
from ..base import ReadOnlySkeletonAdapter
from ..contract import CapabilityState, ProviderCapability


class ServiceTitanAdapter(ReadOnlySkeletonAdapter):
    """Live transport requires a ServiceTitan application and tenant grant."""

    provider = ProviderKey("servicetitan")
    capabilities = tuple(
        ProviderCapability(domain, CapabilityState.REQUIRES_APPROVAL, resource)
        for domain, resource in (
            (Domain.CUSTOMERS, "CRM customers/contacts"),
            (Domain.LOCATIONS, "CRM locations"),
            (Domain.EMPLOYEES, "settings technicians/employees"),
            (Domain.JOBS, "JPM jobs"),
            (Domain.APPOINTMENTS, "JPM appointments"),
            (Domain.DISPATCH, "dispatch capacity/teams"),
            (Domain.ESTIMATES, "sales estimates"),
            (Domain.PRICE_BOOK, "pricebook services/materials"),
            (Domain.INVOICES, "accounting invoices"),
            (Domain.PAYMENTS, "accounting payments"),
        )
    )
