from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.financials.models import (
    Estimate,
    EstimateLineItem,
    Invoice,
    InvoiceLineItem,
    Payment,
)
from app.jobs.models import Job


class FinancialRepository:
    @staticmethod
    async def get_job(
        session: AsyncSession, *, company_id: UUID, branch_id: UUID, job_id: UUID
    ) -> Job | None:
        job = await session.get(Job, job_id)
        if job is None or job.company_id != company_id or job.branch_id != branch_id:
            return None
        return job

    @staticmethod
    async def get_invoice(
        session: AsyncSession, *, company_id: UUID, branch_id: UUID, invoice_id: UUID
    ) -> Invoice | None:
        invoice = await session.get(Invoice, invoice_id)
        if (
            invoice is None
            or invoice.company_id != company_id
            or invoice.branch_id != branch_id
        ):
            return None
        return invoice

    @staticmethod
    def add_estimate(
        session: AsyncSession, estimate: Estimate, items: list[EstimateLineItem]
    ) -> None:
        session.add(estimate)
        session.add_all(items)

    @staticmethod
    def add_invoice(
        session: AsyncSession, invoice: Invoice, items: list[InvoiceLineItem]
    ) -> None:
        session.add(invoice)
        session.add_all(items)

    @staticmethod
    def add_payment(session: AsyncSession, payment: Payment) -> None:
        session.add(payment)
