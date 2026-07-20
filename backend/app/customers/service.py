from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.errors import CustomerChildNotFoundError, CustomerNotFoundError
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.customers.normalization import (
    build_normalized_address,
    normalize_email,
    normalize_phone,
    normalize_search_text,
)
from app.customers.repository import CustomerRepository
from app.customers.schemas import (
    ContactCreate,
    ContactUpdate,
    CustomerCreate,
    ServiceLocationCreate,
    ServiceLocationUpdate,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import AuthorizationContext


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def values_for_model(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.value if hasattr(value, "value") else value
        for key, value in values.items()
    }


class CustomerService:
    @staticmethod
    def _stage_event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        entity_type: str,
        entity_id: UUID,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                user_id=context.user.id,
                payload=payload,
            ),
        )

    @staticmethod
    async def _customer_for_update(
        session: AsyncSession,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> Customer:
        customer = await CustomerRepository.get(
            session,
            company_id=context.company.id,
            customer_id=customer_id,
            for_update=True,
        )
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        return customer

    async def list_customers(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Customer], int]:
        return await CustomerRepository.list_customers(
            session,
            company_id=context.company.id,
            search=search,
            limit=limit,
            offset=offset,
        )

    async def get_customer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> Customer:
        customer = await CustomerRepository.get(
            session,
            company_id=context.company.id,
            customer_id=customer_id,
            with_relationships=True,
        )
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        return customer

    async def create_customer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: CustomerCreate,
    ) -> Customer:
        async with session.begin():
            customer_number = await CustomerRepository.next_customer_number(
                session, context.company.id
            )
            values = values_for_model(data.model_dump())
            customer = Customer(
                **values,
                company_id=context.company.id,
                customer_number=customer_number,
                normalized_name=normalize_search_text(data.display_name),
            )
            session.add(customer)
            await session.flush()
            self._stage_event(
                session,
                context=context,
                event_type=EventType.CUSTOMER_CREATED,
                entity_type="customer",
                entity_id=customer.id,
                payload={
                    "customer_number": customer.customer_number,
                    "customer_type": customer.customer_type,
                    "status": customer.status,
                },
            )
        return await self.get_customer(
            session, context=context, customer_id=customer.id
        )

    async def list_contacts(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> list[CustomerContact]:
        await self.get_customer(session, context=context, customer_id=customer_id)
        return await CustomerRepository.list_contacts(
            session, company_id=context.company.id, customer_id=customer_id
        )

    async def add_contact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        data: ContactCreate,
    ) -> CustomerContact:
        async with session.begin():
            customer = await self._customer_for_update(session, context, customer_id)
            if data.is_preferred:
                await CustomerRepository.clear_preferred_contacts(
                    session, customer_id=customer.id
                )
            contact = CustomerContact(
                customer_id=customer.id,
                first_name=data.first_name,
                last_name=data.last_name,
                title=data.title,
                email=data.email,
                normalized_email=normalize_email(data.email) if data.email else None,
                mobile_phone=data.mobile_phone,
                normalized_mobile_phone=(
                    normalize_phone(data.mobile_phone) if data.mobile_phone else None
                ),
                office_phone=data.office_phone,
                normalized_office_phone=(
                    normalize_phone(data.office_phone) if data.office_phone else None
                ),
                is_preferred=data.is_preferred,
                active=data.active,
                notes=data.notes,
            )
            session.add(contact)
            await session.flush()
            if contact.is_preferred:
                customer.primary_contact_id = contact.id
            self._stage_event(
                session,
                context=context,
                event_type=EventType.CONTACT_CREATED,
                entity_type="contact",
                entity_id=contact.id,
                payload={
                    "customer_id": str(customer.id),
                    "is_preferred": contact.is_preferred,
                },
            )
        return contact

    async def update_contact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        contact_id: UUID,
        data: ContactUpdate,
    ) -> CustomerContact:
        changes = data.model_dump(exclude_unset=True)
        if changes.get("active") is False and "is_preferred" not in changes:
            changes["is_preferred"] = False
        async with session.begin():
            customer = await self._customer_for_update(session, context, customer_id)
            contact = await CustomerRepository.get_contact(
                session,
                company_id=context.company.id,
                customer_id=customer.id,
                contact_id=contact_id,
                for_update=True,
            )
            if contact is None:
                raise CustomerChildNotFoundError("Contact", contact_id)
            candidate = ContactCreate(
                **{
                    field: changes.get(field, getattr(contact, field))
                    for field in ContactCreate.model_fields
                }
            )
            validated = candidate.model_dump()
            if validated["is_preferred"]:
                await CustomerRepository.clear_preferred_contacts(
                    session, customer_id=customer.id, exclude_id=contact.id
                )
            changed_fields: list[str] = []
            was_active = contact.active
            for field in changes:
                value = validated[field]
                if getattr(contact, field) != value:
                    setattr(contact, field, value)
                    changed_fields.append(field)
            if "email" in changed_fields:
                contact.normalized_email = (
                    normalize_email(contact.email) if contact.email else None
                )
            if "mobile_phone" in changed_fields:
                contact.normalized_mobile_phone = (
                    normalize_phone(contact.mobile_phone)
                    if contact.mobile_phone
                    else None
                )
            if "office_phone" in changed_fields:
                contact.normalized_office_phone = (
                    normalize_phone(contact.office_phone)
                    if contact.office_phone
                    else None
                )
            if contact.is_preferred and contact.active:
                customer.primary_contact_id = contact.id
            elif customer.primary_contact_id == contact.id:
                customer.primary_contact_id = None
                contact.is_preferred = False
                if "is_preferred" not in changed_fields:
                    changed_fields.append("is_preferred")
            if changed_fields:
                contact.updated_at = utc_now()
                event_type = (
                    EventType.CONTACT_DEACTIVATED
                    if was_active and not contact.active
                    else EventType.CONTACT_UPDATED
                )
                self._stage_event(
                    session,
                    context=context,
                    event_type=event_type,
                    entity_type="contact",
                    entity_id=contact.id,
                    payload={
                        "customer_id": str(customer.id),
                        "changed_fields": sorted(changed_fields),
                    },
                )
        return contact

    async def list_locations(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> list[ServiceLocation]:
        await self.get_customer(session, context=context, customer_id=customer_id)
        return await CustomerRepository.list_locations(
            session, company_id=context.company.id, customer_id=customer_id
        )

    async def add_location(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        data: ServiceLocationCreate,
    ) -> ServiceLocation:
        async with session.begin():
            customer = await self._customer_for_update(session, context, customer_id)
            values = data.model_dump()
            location = ServiceLocation(
                customer_id=customer.id,
                **values,
                normalized_address=build_normalized_address(
                    data.address,
                    data.address_line_2,
                    data.city,
                    data.state,
                    data.postal_code,
                ),
            )
            session.add(location)
            await session.flush()
            self._stage_event(
                session,
                context=context,
                event_type=EventType.SERVICE_LOCATION_CREATED,
                entity_type="service_location",
                entity_id=location.id,
                payload={"customer_id": str(customer.id)},
            )
        return location

    async def update_location(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        location_id: UUID,
        data: ServiceLocationUpdate,
    ) -> ServiceLocation:
        changes = data.model_dump(exclude_unset=True)
        async with session.begin():
            customer = await self._customer_for_update(session, context, customer_id)
            location = await CustomerRepository.get_location(
                session,
                company_id=context.company.id,
                customer_id=customer.id,
                location_id=location_id,
                for_update=True,
            )
            if location is None:
                raise CustomerChildNotFoundError("Service Location", location_id)
            candidate = ServiceLocationCreate(
                **{
                    field: changes.get(field, getattr(location, field))
                    for field in ServiceLocationCreate.model_fields
                }
            )
            validated = candidate.model_dump()
            changed_fields: list[str] = []
            was_active = location.active
            for field in changes:
                value = validated[field]
                if getattr(location, field) != value:
                    setattr(location, field, value)
                    changed_fields.append(field)
            if {
                "address",
                "address_line_2",
                "city",
                "state",
                "postal_code",
            }.intersection(changed_fields):
                location.normalized_address = build_normalized_address(
                    location.address,
                    location.address_line_2,
                    location.city,
                    location.state,
                    location.postal_code,
                )
            if changed_fields:
                location.updated_at = utc_now()
                event_type = (
                    EventType.SERVICE_LOCATION_DEACTIVATED
                    if was_active and not location.active
                    else EventType.SERVICE_LOCATION_UPDATED
                )
                self._stage_event(
                    session,
                    context=context,
                    event_type=event_type,
                    entity_type="service_location",
                    entity_id=location.id,
                    payload={
                        "customer_id": str(customer.id),
                        "changed_fields": sorted(changed_fields),
                    },
                )
        return location


customer_service = CustomerService()
