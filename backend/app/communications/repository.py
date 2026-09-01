from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, CustomerContact
from app.events.models import BusinessEvent
from app.platform.notifications.models import (
    NotificationDeliveryEvidence,
    NotificationOutbox,
)


class CommunicationRepository:
    @staticmethod
    async def source_event(
        session: AsyncSession, *, event_id: UUID, company_id: UUID, branch_id: UUID
    ) -> BusinessEvent | None:
        return await session.scalar(
            select(BusinessEvent).where(
                BusinessEvent.id == event_id,
                BusinessEvent.company_id == company_id,
                BusinessEvent.branch_id == branch_id,
            )
        )

    @staticmethod
    async def customer_contact(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
        contact_id: UUID,
    ) -> tuple[Customer, CustomerContact] | None:
        row = (
            await session.execute(
                select(Customer, CustomerContact)
                .join(CustomerContact, CustomerContact.customer_id == Customer.id)
                .where(
                    Customer.id == customer_id,
                    Customer.company_id == company_id,
                    Customer.archived_at.is_(None),
                    CustomerContact.id == contact_id,
                    CustomerContact.active.is_(True),
                    CustomerContact.archived_at.is_(None),
                )
            )
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    @staticmethod
    async def latest_consent(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
        channel: str,
    ) -> BusinessEvent | None:
        return await session.scalar(
            select(BusinessEvent)
            .where(
                BusinessEvent.company_id == company_id,
                BusinessEvent.event_type == "customer.consent_recorded",
                BusinessEvent.entity_type == "customer",
                BusinessEvent.entity_id == customer_id,
                BusinessEvent.payload["channel"].astext == channel,
            )
            .order_by(BusinessEvent.occurred_at.desc(), BusinessEvent.id.desc())
            .limit(1)
        )

    @staticmethod
    async def by_identity(
        session: AsyncSession, *, company_id: UUID, request_identity: str
    ) -> NotificationOutbox | None:
        return await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.company_id == company_id,
                NotificationOutbox.idempotency_key == request_identity,
            )
        )

    @staticmethod
    async def list_scoped(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        customer_id: UUID | None,
        limit: int,
    ) -> list[NotificationOutbox]:
        statement: Select[tuple[NotificationOutbox]] = select(NotificationOutbox).where(
            NotificationOutbox.notification_type.like("communications.%"),
            NotificationOutbox.company_id == company_id,
        )
        if branch_id is not None:
            statement = statement.where(NotificationOutbox.branch_id == branch_id)
        if customer_id is not None:
            statement = statement.where(
                NotificationOutbox.payload["customer_id"].astext == str(customer_id)
            )
        statement = statement.order_by(
            NotificationOutbox.created_at.desc(), NotificationOutbox.id.desc()
        ).limit(limit)
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def delivery_evidence(
        session: AsyncSession, *, outbox_id: UUID
    ) -> list[NotificationDeliveryEvidence]:
        return list(
            (
                await session.scalars(
                    select(NotificationDeliveryEvidence)
                    .where(NotificationDeliveryEvidence.outbox_id == outbox_id)
                    .order_by(NotificationDeliveryEvidence.sequence)
                )
            ).all()
        )


communication_repository = CommunicationRepository()
