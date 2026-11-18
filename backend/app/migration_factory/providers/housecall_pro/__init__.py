from ...domain import Domain, ProviderKey
from ..base import ReadOnlySkeletonAdapter
from ..contract import CapabilityState, ProviderCapability


class HousecallProAdapter(ReadOnlySkeletonAdapter):
    provider = ProviderKey("housecall_pro")
    capabilities = tuple(
        ProviderCapability(domain, CapabilityState.AVAILABLE_API, resource)
        for domain, resource in (
            (Domain.CUSTOMERS, "customers"),
            (Domain.LOCATIONS, "customer/job addresses"),
            (Domain.EMPLOYEES, "employees"),
            (Domain.JOBS, "jobs"),
            (Domain.APPOINTMENTS, "job appointments"),
            (Domain.ESTIMATES, "estimates"),
            (Domain.INVOICES, "invoices"),
            (Domain.PAYMENTS, "invoice payment/refund assertions"),
        )
    )
