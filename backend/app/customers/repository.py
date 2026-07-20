from datetime import datetime
from uuid import UUID

from sqlalchemy import asc, desc, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.customers.models import (
    Customer,
    CustomerContact,
    CustomerNumberSequence,
    ServiceLocation,
)
from app.customers.schemas import CustomerSearchQuery, CustomerSortField, SortDirection


class CustomerRepository:
    @staticmethod
    def apply_updates(customer: Customer, changes: dict[str, object]) -> list[str]:
        """Apply an allowlisted Customer mutation to a locked ORM record."""
        allowed_fields = {
            "display_name",
            "legal_name",
            "status",
            "customer_type",
            "preferred_contact_method",
            "normalized_name",
            "updated_at",
        }
        unexpected = changes.keys() - allowed_fields
        if unexpected:
            raise ValueError(
                f"Unsupported Customer update fields: {sorted(unexpected)}"
            )
        changed_fields: list[str] = []
        for field, value in changes.items():
            if getattr(customer, field) != value:
                setattr(customer, field, value)
                changed_fields.append(field)
        return changed_fields

    @staticmethod
    async def get_for_lifecycle(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
    ) -> Customer | None:
        """Lock an active or archived Customer for a lifecycle transition."""
        return await session.scalar(
            select(Customer)
            .where(
                Customer.id == customer_id,
                Customer.company_id == company_id,
            )
            .with_for_update()
        )

    @staticmethod
    def set_archive_state(
        customer: Customer,
        *,
        archived_at: datetime | None,
        updated_at: datetime,
    ) -> None:
        customer.archived_at = archived_at
        customer.updated_at = updated_at

    @staticmethod
    async def next_customer_number(session: AsyncSession, company_id: UUID) -> str:
        statement = (
            insert(CustomerNumberSequence)
            .values(company_id=company_id, last_value=1)
            .on_conflict_do_update(
                index_elements=[CustomerNumberSequence.company_id],
                set_={
                    "last_value": CustomerNumberSequence.last_value + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(CustomerNumberSequence.last_value)
        )
        value = await session.scalar(statement)
        if value is None:
            raise RuntimeError("Customer number allocation failed")
        return f"CUS-{value:06d}"

    @staticmethod
    async def get(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
        with_relationships: bool = False,
        for_update: bool = False,
    ) -> Customer | None:
        statement = select(Customer).where(
            Customer.id == customer_id,
            Customer.company_id == company_id,
            Customer.archived_at.is_(None),
        )
        if with_relationships:
            statement = statement.options(
                selectinload(Customer.contacts),
                selectinload(Customer.locations),
            )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    async def get_detail(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
    ) -> Customer | None:
        """Load the Customer aggregate in a fixed number of queries."""
        statement = (
            select(Customer)
            .where(
                Customer.id == customer_id,
                Customer.company_id == company_id,
                Customer.archived_at.is_(None),
            )
            .options(
                joinedload(Customer.primary_contact),
                selectinload(Customer.contacts),
                selectinload(Customer.locations),
            )
        )
        return await session.scalar(statement)

    @staticmethod
    async def list_customers(
        session: AsyncSession,
        *,
        company_id: UUID,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Customer], int]:
        filters = [
            Customer.company_id == company_id,
            Customer.archived_at.is_(None),
        ]
        if search:
            query = f"%{search.strip()}%"
            filters.append(
                or_(
                    Customer.customer_number.ilike(query),
                    Customer.display_name.ilike(query),
                    Customer.legal_name.ilike(query),
                )
            )
        total = await session.scalar(
            select(func.count()).select_from(Customer).where(*filters)
        )
        records = list(
            (
                await session.scalars(
                    select(Customer)
                    .where(*filters)
                    .order_by(Customer.display_name, Customer.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        return records, int(total or 0)

    @staticmethod
    async def search_customers(
        session: AsyncSession,
        *,
        company_id: UUID,
        criteria: CustomerSearchQuery,
    ) -> tuple[list[Customer], int]:
        filters = [
            Customer.company_id == company_id,
            Customer.archived_at.is_(None),
        ]
        preferred_contact_exists = exists(
            select(1).where(
                CustomerContact.customer_id == Customer.id,
                CustomerContact.active.is_(True),
                CustomerContact.is_preferred.is_(True),
                CustomerContact.archived_at.is_(None),
            )
        )
        active_location_exists = exists(
            select(1).where(
                ServiceLocation.customer_id == Customer.id,
                ServiceLocation.active.is_(True),
                ServiceLocation.archived_at.is_(None),
            )
        )

        if criteria.query:
            raw = criteria.query.strip()
            text_pattern = f"%{raw}%"
            lowered_pattern = f"%{raw.lower()}%"
            digits = "".join(character for character in raw if character.isdigit())
            contact_matches = [
                func.concat_ws(
                    " ", CustomerContact.first_name, CustomerContact.last_name
                ).ilike(text_pattern),
                CustomerContact.normalized_email.ilike(lowered_pattern),
            ]
            if digits:
                phone_pattern = f"%{digits}%"
                contact_matches.extend(
                    [
                        CustomerContact.normalized_mobile_phone.ilike(phone_pattern),
                        CustomerContact.normalized_office_phone.ilike(phone_pattern),
                    ]
                )
            filters.append(
                or_(
                    Customer.customer_number.ilike(text_pattern),
                    Customer.display_name.ilike(text_pattern),
                    Customer.legal_name.ilike(text_pattern),
                    exists(
                        select(1).where(
                            CustomerContact.customer_id == Customer.id,
                            or_(*contact_matches),
                        )
                    ),
                    exists(
                        select(1).where(
                            ServiceLocation.customer_id == Customer.id,
                            or_(
                                ServiceLocation.address.ilike(text_pattern),
                                ServiceLocation.address_line_2.ilike(text_pattern),
                                ServiceLocation.city.ilike(text_pattern),
                                ServiceLocation.postal_code.ilike(text_pattern),
                            ),
                        )
                    ),
                )
            )
        if criteria.status is not None:
            filters.append(Customer.status == criteria.status.value)
        if criteria.customer_type is not None:
            filters.append(Customer.customer_type == criteria.customer_type.value)
        if criteria.has_preferred_contact is not None:
            filters.append(
                preferred_contact_exists
                if criteria.has_preferred_contact
                else ~preferred_contact_exists
            )
        if criteria.has_active_service_locations is not None:
            filters.append(
                active_location_exists
                if criteria.has_active_service_locations
                else ~active_location_exists
            )
        if criteria.created_from is not None:
            filters.append(Customer.created_at >= criteria.created_from)
        if criteria.created_to is not None:
            filters.append(Customer.created_at <= criteria.created_to)
        if criteria.updated_from is not None:
            filters.append(Customer.updated_at >= criteria.updated_from)
        if criteria.updated_to is not None:
            filters.append(Customer.updated_at <= criteria.updated_to)

        sort_columns = {
            CustomerSortField.CUSTOMER_NUMBER: Customer.customer_number,
            CustomerSortField.DISPLAY_NAME: Customer.display_name,
            CustomerSortField.CREATED_AT: Customer.created_at,
            CustomerSortField.UPDATED_AT: Customer.updated_at,
            CustomerSortField.STATUS: Customer.status,
        }
        direction = asc if criteria.sort_direction is SortDirection.ASC else desc
        total = await session.scalar(
            select(func.count()).select_from(Customer).where(*filters)
        )
        records = list(
            (
                await session.scalars(
                    select(Customer)
                    .where(*filters)
                    .order_by(
                        direction(sort_columns[criteria.sort_by]),
                        direction(Customer.id),
                    )
                    .limit(criteria.page_size)
                    .offset((criteria.page - 1) * criteria.page_size)
                )
            ).all()
        )
        return records, int(total or 0)

    @staticmethod
    async def get_contact(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
        contact_id: UUID,
        for_update: bool = False,
    ) -> CustomerContact | None:
        statement = (
            select(CustomerContact)
            .join(Customer, Customer.id == CustomerContact.customer_id)
            .where(
                CustomerContact.id == contact_id,
                CustomerContact.customer_id == customer_id,
                Customer.company_id == company_id,
                Customer.archived_at.is_(None),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    async def list_contacts(
        session: AsyncSession, *, company_id: UUID, customer_id: UUID
    ) -> list[CustomerContact]:
        return list(
            (
                await session.scalars(
                    select(CustomerContact)
                    .join(Customer, Customer.id == CustomerContact.customer_id)
                    .where(
                        CustomerContact.customer_id == customer_id,
                        Customer.company_id == company_id,
                        Customer.archived_at.is_(None),
                    )
                    .order_by(
                        CustomerContact.is_preferred.desc(),
                        CustomerContact.last_name,
                        CustomerContact.first_name,
                        CustomerContact.id,
                    )
                )
            ).all()
        )

    @staticmethod
    async def clear_preferred_contacts(
        session: AsyncSession, *, customer_id: UUID, exclude_id: UUID | None = None
    ) -> None:
        records = list(
            (
                await session.scalars(
                    select(CustomerContact)
                    .where(
                        CustomerContact.customer_id == customer_id,
                        CustomerContact.is_preferred.is_(True),
                        CustomerContact.active.is_(True),
                    )
                    .with_for_update()
                )
            ).all()
        )
        for record in records:
            if record.id != exclude_id:
                record.is_preferred = False

    @staticmethod
    async def get_location(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
        location_id: UUID,
        for_update: bool = False,
    ) -> ServiceLocation | None:
        statement = (
            select(ServiceLocation)
            .join(Customer, Customer.id == ServiceLocation.customer_id)
            .where(
                ServiceLocation.id == location_id,
                ServiceLocation.customer_id == customer_id,
                Customer.company_id == company_id,
                Customer.archived_at.is_(None),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    async def list_locations(
        session: AsyncSession, *, company_id: UUID, customer_id: UUID
    ) -> list[ServiceLocation]:
        return list(
            (
                await session.scalars(
                    select(ServiceLocation)
                    .join(Customer, Customer.id == ServiceLocation.customer_id)
                    .where(
                        ServiceLocation.customer_id == customer_id,
                        Customer.company_id == company_id,
                        Customer.archived_at.is_(None),
                    )
                    .order_by(ServiceLocation.nickname, ServiceLocation.id)
                )
            ).all()
        )
