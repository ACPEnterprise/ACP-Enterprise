from ...domain import Domain, ProviderKey
from ..base import ReadOnlySkeletonAdapter
from ..contract import CapabilityState, ProviderCapability


class JobberAdapter(ReadOnlySkeletonAdapter):
    """Live transport requires an approved Jobber OAuth application."""

    provider = ProviderKey("jobber")
    capabilities = tuple(
        ProviderCapability(domain, CapabilityState.REQUIRES_APPROVAL, resource)
        for domain, resource in (
            (Domain.CUSTOMERS, "GraphQL clients"),
            (Domain.LOCATIONS, "GraphQL properties"),
            (Domain.EMPLOYEES, "GraphQL users"),
            (Domain.JOBS, "GraphQL jobs"),
            (Domain.APPOINTMENTS, "GraphQL visits"),
            (Domain.ESTIMATES, "GraphQL quotes"),
            (Domain.INVOICES, "GraphQL invoices"),
            (Domain.PAYMENTS, "GraphQL payments"),
            (Domain.PRICE_BOOK, "GraphQL products/services"),
            (Domain.TIMEKEEPING, "GraphQL time sheets"),
        )
    )
