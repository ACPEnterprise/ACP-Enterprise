"""Minimum-necessary assignment-scoped projections for ACP Employee."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import CustomerContact
from app.field_service.errors import FieldServiceNotFound
from app.field_service.schemas import (
    FieldCommunicationState,
    FieldContact,
    FieldInvoice,
    FieldJobSources,
    FieldPaymentState,
    FieldPriceBookItem,
)
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.payments.models import PaymentIntent, PaymentReceipt
from app.platform.notifications.models import NotificationOutbox
from app.platform.permissions.authorization import AuthorizationContext
from app.price_book.models import PriceBookPriceVersion, PriceBookServiceItem

from .service import FieldService


class FieldSourceService:
    def __init__(self, field: FieldService) -> None:
        self.field = field

    async def job_sources(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
    ) -> FieldJobSources:
        assignment = await self.field._assigned_job(session, context, job_id)
        job = await session.scalar(
            select(Job).where(
                Job.company_id == context.company.id,
                Job.branch_id == assignment.branch_id,
                Job.id == job_id,
            )
        )

        if job is None:
            raise FieldServiceNotFound("Assigned field Job was not found.")
        contact = await self._contact(session, job.customer_id)
        invoice_record = await session.scalar(
            select(Invoice)
            .where(
                Invoice.company_id == context.company.id,
                Invoice.branch_id == assignment.branch_id,
                Invoice.job_id == job_id,
            )
            .order_by(Invoice.created_at.desc())
            .limit(1)
        )
        invoice = self._invoice(invoice_record)
        payment = await self._payment(session, context.company.id, invoice_record)
        communications = await self._communications(
            session, context.company.id, job_id
        )
        completion = await self.field.state(session, context=context, job_id=job_id)
        return FieldJobSources(
            job_id=job.id,
            assignment_id=assignment.id,
            assignment_version=assignment.version,
            customer_id=job.customer_id,
            service_location_id=job.service_location_id,
            contact=contact,
            invoice=invoice,
            payment=payment,
            communications=communications,
            completion=completion,
        )

    async def price_book(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        limit: int,
    ) -> tuple[FieldPriceBookItem, ...]:
        assignment = await self.field._assigned_job(session, context, job_id)
        records = (
            await session.execute(
                select(PriceBookServiceItem, PriceBookPriceVersion)
                .join(
                    PriceBookPriceVersion,
                    (PriceBookPriceVersion.company_id == PriceBookServiceItem.company_id)
                    & (PriceBookPriceVersion.id == PriceBookServiceItem.current_version_id),
                )
                .where(
                    PriceBookServiceItem.company_id == context.company.id,
                    PriceBookServiceItem.status == "active",
                    or_(
                        PriceBookServiceItem.branch_id.is_(None),
                        PriceBookServiceItem.branch_id == assignment.branch_id,
                    ),
                    PriceBookPriceVersion.status == "active",
                    or_(
                        PriceBookPriceVersion.branch_id.is_(None),
                        PriceBookPriceVersion.branch_id == assignment.branch_id,
                    ),
                )
                .order_by(PriceBookServiceItem.name, PriceBookServiceItem.id)
                .limit(limit)
            )
        ).all()
        return tuple(
            FieldPriceBookItem(
                item_id=item.id,
                code=item.code,
                name=item.name,
                customer_description=item.customer_description,
                price_version_id=version.id,
                unit_price=version.unit_price,
                currency=version.currency,
            )
            for item, version in records
        )

    @staticmethod
    async def _contact(session: AsyncSession, customer_id: UUID) -> FieldContact | None:
        contact = await session.scalar(
            select(CustomerContact)
            .where(
                CustomerContact.customer_id == customer_id,
                CustomerContact.active.is_(True),
                CustomerContact.archived_at.is_(None),
            )
            .order_by(CustomerContact.is_preferred.desc(), CustomerContact.created_at)
            .limit(1)
        )
        if contact is None:
            return None
        return FieldContact(
            contact_id=contact.id,
            display_name=f"{contact.first_name} {contact.last_name}".strip(),
            phone=contact.mobile_phone or contact.office_phone,
            email=contact.email,
            can_approve_work=contact.can_approve_work,
        )

    @staticmethod
    def _invoice(invoice: Invoice | None) -> FieldInvoice | None:
        if invoice is None:
            return None
        return FieldInvoice(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            status=invoice.status,
            version=invoice.version,
            open_amount=invoice.open_amount,
            currency=invoice.currency,
        )

    @staticmethod
    async def _payment(
        session: AsyncSession, company_id: UUID, invoice: Invoice | None
    ) -> FieldPaymentState:
        if invoice is None:
            return FieldPaymentState(
                state="invoice_not_available",
                invoice_id=None,
                open_amount=None,
                currency=None,
                receipt_status=None,
            )
        intent = await session.scalar(
            select(PaymentIntent)
            .where(
                PaymentIntent.company_id == company_id,
                PaymentIntent.invoice_id == invoice.id,
            )
            .order_by(PaymentIntent.created_at.desc())
            .limit(1)
        )
        receipt = (
            await session.scalar(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.company_id == company_id,
                    PaymentReceipt.intent_id == intent.id,
                )
                .limit(1)
            )
            if intent
            else None
        )
        return FieldPaymentState(
            state=intent.status if intent else "no_accepted_payment_evidence",
            invoice_id=invoice.id,
            open_amount=invoice.open_amount,
            currency=invoice.currency,
            receipt_status=receipt.status if receipt else None,
        )

    @staticmethod
    async def _communications(
        session: AsyncSession, company_id: UUID, job_id: UUID
    ) -> tuple[FieldCommunicationState, ...]:
        records = tuple(
            (
                await session.scalars(
                    select(NotificationOutbox)
                    .where(
                        NotificationOutbox.company_id == company_id,
                        NotificationOutbox.notification_type.like("communications.%"),
                        NotificationOutbox.payload["source_entity_id"].astext
                        == str(job_id),
                    )
                    .order_by(NotificationOutbox.created_at.desc())
                    .limit(25)
                )
            ).all()
        )
        return tuple(
            FieldCommunicationState(
                communication_id=record.id,
                message_class=str(record.payload.get("communication_type", "unknown")),
                channel=record.channel or "unknown",
                state=("delivered" if record.status == "sent" else "uncertain" if record.status == "ambiguous" else record.status),
                created_at=record.created_at,
            )
            for record in records
        )

field_source_service = FieldSourceService(FieldService())
