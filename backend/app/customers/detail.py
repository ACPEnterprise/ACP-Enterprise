from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.errors import CustomerNotFoundError
from app.customers.models import CustomerContact, ServiceLocation
from app.customers.repository import CustomerRepository
from app.customers.schemas import (
    ContactResponse,
    CustomerDetailMetadata,
    CustomerDetailResponse,
    CustomerResponse,
    CustomerStatus,
    CustomerType,
    PreferredContactMethod,
    ServiceLocationResponse,
)
from app.platform.permissions.authorization import AuthorizationContext


class CustomerDetailService:
    """Assemble the canonical Customer detail read model.

    Future operational modules can extend ``CustomerDetailResponse`` with their
    own typed sections while this service remains the aggregate orchestrator.
    Each module must retain repository ownership of its database queries.
    """

    async def get_detail(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> CustomerDetailResponse:
        customer = await CustomerRepository.get_detail(
            session,
            company_id=context.company.id,
            customer_id=customer_id,
        )
        if customer is None:
            raise CustomerNotFoundError(customer_id)

        contacts = sorted(customer.contacts, key=self._contact_sort_key)
        locations = sorted(customer.locations, key=self._location_sort_key)
        preferred_contact = self._preferred_contact(customer.primary_contact, contacts)
        customer_response = CustomerResponse.model_validate(customer)
        location_responses = [
            ServiceLocationResponse.model_validate(location) for location in locations
        ]
        return CustomerDetailResponse(
            **customer_response.model_dump(),
            preferred_contact=(
                ContactResponse.model_validate(preferred_contact)
                if preferred_contact is not None
                else None
            ),
            contacts=[ContactResponse.model_validate(contact) for contact in contacts],
            locations=location_responses,
            active_service_locations=[
                response
                for response, location in zip(
                    location_responses, locations, strict=True
                )
                if location.active and location.archived_at is None
            ],
            inactive_service_locations=[
                response
                for response, location in zip(
                    location_responses, locations, strict=True
                )
                if not location.active or location.archived_at is not None
            ],
            metadata=CustomerDetailMetadata(
                company_id=customer.company_id,
                customer_number=customer.customer_number,
                status=CustomerStatus(customer.status),
                customer_type=CustomerType(customer.customer_type),
                preferred_contact_method=PreferredContactMethod(
                    customer.preferred_contact_method
                ),
                created_at=customer.created_at,
                updated_at=customer.updated_at,
            ),
        )

    @staticmethod
    def _preferred_contact(
        primary_contact: CustomerContact | None,
        contacts: list[CustomerContact],
    ) -> CustomerContact | None:
        if (
            primary_contact is not None
            and primary_contact.active
            and primary_contact.archived_at is None
        ):
            return primary_contact
        return next(
            (
                contact
                for contact in contacts
                if contact.is_preferred
                and contact.active
                and contact.archived_at is None
            ),
            None,
        )

    @staticmethod
    def _contact_sort_key(contact: CustomerContact) -> tuple[bool, str, str, str]:
        return (
            not contact.is_preferred,
            contact.last_name.casefold(),
            contact.first_name.casefold(),
            str(contact.id),
        )

    @staticmethod
    def _location_sort_key(location: ServiceLocation) -> tuple[bool, str, str]:
        return (
            not location.active,
            (location.nickname or location.address).casefold(),
            str(location.id),
        )


customer_detail_service = CustomerDetailService()
