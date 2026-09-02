from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, CustomerContact
from app.dispatch.models import DispatchAssignment
from app.estimates.models import Estimate
from app.events.models import BusinessEvent
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.platform.notifications.models import (
    NotificationDeliveryEvidence,
    NotificationOutbox,
)
from app.scheduling.models import Appointment
from app.service_agreements.models import AgreementBillingOccurrence, ServiceAgreement

from .suppression import recipient_suppression_repository
from .types import CommunicationChannel, CommunicationPurpose


class CommunicationRepository:
    @staticmethod
    async def is_recipient_suppressed(
        session: AsyncSession,
        *,
        company_id: UUID,
        channel: CommunicationChannel,
        destination_digest_value: str,
        purpose: CommunicationPurpose,
    ) -> bool:
        return await recipient_suppression_repository.is_suppressed(
            session,
            company_id=company_id,
            channel=channel,
            destination_digest_value=destination_digest_value,
            purpose=purpose,
        )

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
    async def source_customer_id(
        session: AsyncSession,
        *,
        source: BusinessEvent,
        company_id: UUID,
        branch_id: UUID,
    ) -> UUID | None:
        """Resolve Customer authority from the source aggregate, never caller input."""
        recorded_customer = source.payload.get("customer_id")
        if recorded_customer is not None:
            try:
                return UUID(str(recorded_customer))
            except ValueError:
                return None
        scope = (company_id, branch_id, source.entity_id)
        if source.entity_type == "appointment":
            return await session.scalar(
                select(Appointment.customer_id).where(
                    Appointment.company_id == scope[0],
                    Appointment.branch_id == scope[1],
                    Appointment.id == scope[2],
                )
            )
        if source.entity_type == "job":
            return await session.scalar(
                select(Job.customer_id).where(
                    Job.company_id == scope[0],
                    Job.branch_id == scope[1],
                    Job.id == scope[2],
                )
            )
        if source.entity_type == "estimate":
            return await session.scalar(
                select(Estimate.customer_id).where(
                    Estimate.company_id == scope[0],
                    Estimate.branch_id == scope[1],
                    Estimate.id == scope[2],
                )
            )
        if source.entity_type == "invoice":
            return await session.scalar(
                select(Invoice.customer_id).where(
                    Invoice.company_id == scope[0],
                    Invoice.branch_id == scope[1],
                    Invoice.id == scope[2],
                )
            )
        if source.entity_type == "service_agreement":
            return await session.scalar(
                select(ServiceAgreement.customer_id).where(
                    ServiceAgreement.company_id == scope[0],
                    ServiceAgreement.branch_id == scope[1],
                    ServiceAgreement.id == scope[2],
                )
            )
        if source.entity_type == "service_agreement_billing_occurrence":
            return await session.scalar(
                select(ServiceAgreement.customer_id)
                .join(
                    AgreementBillingOccurrence,
                    (
                        AgreementBillingOccurrence.company_id
                        == ServiceAgreement.company_id
                    )
                    & (AgreementBillingOccurrence.agreement_id == ServiceAgreement.id),
                )
                .where(
                    AgreementBillingOccurrence.company_id == scope[0],
                    AgreementBillingOccurrence.branch_id == scope[1],
                    AgreementBillingOccurrence.id == scope[2],
                )
            )
        if source.entity_type == "dispatch_assignment":
            return await session.scalar(
                select(Appointment.customer_id)
                .join(
                    DispatchAssignment,
                    (DispatchAssignment.company_id == Appointment.company_id)
                    & (DispatchAssignment.appointment_id == Appointment.id),
                )
                .where(
                    DispatchAssignment.company_id == scope[0],
                    DispatchAssignment.branch_id == scope[1],
                    DispatchAssignment.id == scope[2],
                    Appointment.branch_id == scope[1],
                )
            )
        return None

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
    async def operations_summary(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
    ) -> dict[str, object]:
        scope = [
            NotificationOutbox.company_id == company_id,
            NotificationOutbox.notification_type.like("communications.%"),
        ]
        if branch_id is not None:
            scope.append(NotificationOutbox.branch_id == branch_id)

        async def count(*statuses: str) -> int:
            value = await session.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(*scope, NotificationOutbox.status.in_(statuses))
            )
            return int(value or 0)

        oldest_pending_at = await session.scalar(
            select(func.min(NotificationOutbox.created_at)).where(
                *scope,
                NotificationOutbox.status.in_(
                    ("pending", "claimed", "retry_scheduled", "accepted")
                ),
            )
        )
        return {
            "pending": await count("pending", "claimed", "retry_scheduled"),
            "accepted_pending_delivery": await count("accepted"),
            "delivered": await count("sent"),
            "needs_attention": await count("failed", "ambiguous"),
            "suppressed": await count("suppressed"),
            "oldest_pending_at": oldest_pending_at,
        }

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
