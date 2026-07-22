from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.repository import CustomerRepository


@dataclass(frozen=True)
class CustomerServiceLocationReference:
    company_id: UUID
    customer_id: UUID
    service_location_id: UUID
    customer_status: str
    service_location_active: bool


class CustomerReferenceService:
    """Expose immutable Customer facts without leaking Customer ORM records."""

    async def get_service_location_reference(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
        service_location_id: UUID,
        for_update: bool = False,
    ) -> CustomerServiceLocationReference | None:
        customer = await CustomerRepository.get(
            session,
            company_id=company_id,
            customer_id=customer_id,
            for_update=for_update,
        )
        if customer is None or customer.status != "active":
            return None
        location = await CustomerRepository.get_location(
            session,
            company_id=company_id,
            customer_id=customer_id,
            location_id=service_location_id,
            for_update=for_update,
        )
        if location is None or not location.active or location.archived_at is not None:
            return None
        return CustomerServiceLocationReference(
            company_id=customer.company_id,
            customer_id=customer.id,
            service_location_id=location.id,
            customer_status=customer.status,
            service_location_active=location.active,
        )


customer_reference_service = CustomerReferenceService()
