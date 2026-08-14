from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.financials.models import (
    Estimate,
    EstimateLineItem,
    Invoice,
    InvoiceLineItem,
    Payment,
    utc_now,
)
from app.financials.repository import FinancialRepository
from app.platform.permissions.authorization import AuthorizationContext


class FinancialValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MigratedLineItem:
    source_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    total_amount: Decimal


@dataclass(frozen=True)
class MigrateEstimate:
    branch_id: UUID
    job_id: UUID
    status: str
    currency: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_items: tuple[MigratedLineItem, ...]
    presented_at: datetime | None = None
    expires_on: date | None = None


@dataclass(frozen=True)
class MigrateInvoice:
    branch_id: UUID
    job_id: UUID
    status: str
    currency: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_items: tuple[MigratedLineItem, ...]
    issued_at: datetime | None = None
    due_on: date | None = None


@dataclass(frozen=True)
class MigratePayment:
    branch_id: UUID
    invoice_id: UUID
    status: str
    currency: str
    amount: Decimal
    paid_at: datetime | None = None
    method: str | None = None
    reference: str | None = None


class FinancialService:
    def __init__(self, repository: FinancialRepository | None = None) -> None:
        self._repository = repository or FinancialRepository()

    @staticmethod
    def _authorize(context: AuthorizationContext, branch_id: UUID) -> None:
        if not context.can_access_branch(branch_id):
            raise FinancialValidationError("Branch is not authorized.")

    @staticmethod
    def _currency(value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise FinancialValidationError("Currency must be a three-letter code.")
        return normalized

    @staticmethod
    def _validate_amounts(subtotal: Decimal, tax: Decimal, total: Decimal) -> None:
        if subtotal < 0 or tax < 0 or total < 0 or subtotal + tax != total:
            raise FinancialValidationError("Financial totals do not reconcile.")

    @staticmethod
    def _validate_items(items: tuple[MigratedLineItem, ...], subtotal: Decimal) -> None:
        if not items:
            raise FinancialValidationError("At least one line item is required.")
        source_ids: set[str] = set()
        calculated = Decimal(0)
        for item in items:
            if not item.source_id.strip() or item.source_id in source_ids:
                raise FinancialValidationError(
                    "Line-item source identifiers must be nonblank and unique."
                )
            source_ids.add(item.source_id)
            if not item.description.strip():
                raise FinancialValidationError("Line-item description is required.")
            if item.quantity <= 0 or item.unit_price < 0:
                raise FinancialValidationError("Line-item amounts are invalid.")
            if item.quantity * item.unit_price != item.total_amount:
                raise FinancialValidationError("Line-item total does not reconcile.")
            calculated += item.total_amount
        if calculated != subtotal:
            raise FinancialValidationError(
                "Line-item totals do not equal the document subtotal."
            )

    @staticmethod
    def _number(prefix: str, identifier: UUID) -> str:
        return f"{prefix}-{identifier.hex[:16].upper()}"

    @staticmethod
    def _event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
        entity_type: str,
        entity_id: UUID,
        event_type: EventType,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=branch_id,
                user_id=context.user.id,
                payload=payload,
            ),
        )

    async def stage_migrated_estimate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: MigrateEstimate,
    ) -> tuple[Estimate, tuple[EstimateLineItem, ...]]:
        self._authorize(context, command.branch_id)
        if command.status not in {
            "draft",
            "presented",
            "approved",
            "declined",
            "expired",
        }:
            raise FinancialValidationError("Estimate status is invalid.")
        self._validate_amounts(
            command.subtotal_amount, command.tax_amount, command.total_amount
        )
        self._validate_items(command.line_items, command.subtotal_amount)
        job = await self._repository.get_job(
            session,
            company_id=context.company.id,
            branch_id=command.branch_id,
            job_id=command.job_id,
        )
        if job is None:
            raise FinancialValidationError("Job parent was not found.")
        identifier = uuid4()
        estimate = Estimate(
            id=identifier,
            company_id=context.company.id,
            branch_id=command.branch_id,
            job_id=job.id,
            customer_id=job.customer_id,
            service_location_id=job.service_location_id,
            estimate_number=self._number("EST", identifier),
            status=command.status,
            currency=self._currency(command.currency),
            subtotal_amount=command.subtotal_amount,
            tax_amount=command.tax_amount,
            total_amount=command.total_amount,
            presented_at=command.presented_at,
            expires_on=command.expires_on,
            created_by_user_id=context.user.id,
            created_at=utc_now(),
        )
        items = [
            EstimateLineItem(
                id=uuid4(),
                company_id=context.company.id,
                estimate_id=estimate.id,
                position=position,
                description=item.description.strip(),
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_amount=item.total_amount,
            )
            for position, item in enumerate(command.line_items, start=1)
        ]
        self._repository.add_estimate(session, estimate, items)
        self._event(
            session,
            context=context,
            branch_id=command.branch_id,
            entity_type="estimate",
            entity_id=estimate.id,
            event_type=EventType.ESTIMATE_MIGRATED,
            payload={"status": estimate.status, "origin": "migration"},
        )
        return estimate, tuple(items)

    async def stage_migrated_invoice(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: MigrateInvoice,
    ) -> tuple[Invoice, tuple[InvoiceLineItem, ...]]:
        self._authorize(context, command.branch_id)
        if command.status not in {"draft", "issued", "partially_paid", "paid", "void"}:
            raise FinancialValidationError("Invoice status is invalid.")
        self._validate_amounts(
            command.subtotal_amount, command.tax_amount, command.total_amount
        )
        self._validate_items(command.line_items, command.subtotal_amount)
        job = await self._repository.get_job(
            session,
            company_id=context.company.id,
            branch_id=command.branch_id,
            job_id=command.job_id,
        )
        if job is None:
            raise FinancialValidationError("Job parent was not found.")
        identifier = uuid4()
        created_at = utc_now()
        issue_date = (command.issued_at or created_at).date()
        due_date = command.due_on or issue_date
        invoice_number = self._number("INV", identifier)
        invoice = Invoice(
            id=identifier,
            company_id=context.company.id,
            branch_id=command.branch_id,
            job_id=job.id,
            customer_id=job.customer_id,
            service_location_id=job.service_location_id,
            invoice_number=invoice_number,
            identity_origin="grandfathered_legacy",
            status="voided" if command.status == "void" else command.status,
            accounting_status="reconciliation_required",
            currency=self._currency(command.currency),
            issue_date=issue_date,
            due_date=due_date,
            terms="Imported invoice terms require source reconciliation",
            subtotal_amount=command.subtotal_amount,
            discount_amount=Decimal("0.00"),
            tax_amount=command.tax_amount,
            total_amount=command.total_amount,
            open_amount=command.total_amount,
            calculation_digest=sha256(
                f"{identifier}:{invoice_number}".encode()
            ).hexdigest(),
            legacy_evidence_missing=True,
            version=1,
            issued_at=command.issued_at,
            due_on=command.due_on,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
            created_at=created_at,
            updated_at=created_at,
        )
        items = [
            InvoiceLineItem(
                id=uuid4(),
                company_id=context.company.id,
                invoice_id=invoice.id,
                position=position,
                title=item.description.strip(),
                description=item.description.strip(),
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_amount=item.total_amount,
                evidence={
                    "legacy_evidence_missing": True,
                    "source_line_id": item.source_id,
                },
                created_at=created_at,
            )
            for position, item in enumerate(command.line_items, start=1)
        ]
        self._repository.add_invoice(session, invoice, items)
        self._event(
            session,
            context=context,
            branch_id=command.branch_id,
            entity_type="invoice",
            entity_id=invoice.id,
            event_type=EventType.INVOICE_MIGRATED,
            payload={"status": invoice.status, "origin": "migration"},
        )
        return invoice, tuple(items)

    async def stage_migrated_payment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: MigratePayment,
    ) -> Payment:
        self._authorize(context, command.branch_id)
        if command.status not in {"pending", "succeeded", "failed", "refunded"}:
            raise FinancialValidationError("Payment status is invalid.")
        if command.amount <= 0:
            raise FinancialValidationError("Payment amount must be positive.")
        invoice = await self._repository.get_invoice(
            session,
            company_id=context.company.id,
            branch_id=command.branch_id,
            invoice_id=command.invoice_id,
        )
        if invoice is None:
            raise FinancialValidationError("Invoice parent was not found.")
        payment = Payment(
            id=uuid4(),
            company_id=context.company.id,
            branch_id=command.branch_id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            amount=command.amount,
            currency=self._currency(command.currency),
            status=command.status,
            paid_at=command.paid_at,
            method=command.method,
            reference=command.reference,
            created_by_user_id=context.user.id,
            created_at=utc_now(),
        )
        self._repository.add_payment(session, payment)
        self._event(
            session,
            context=context,
            branch_id=command.branch_id,
            entity_type="payment",
            entity_id=payment.id,
            event_type=EventType.PAYMENT_MIGRATED,
            payload={"status": payment.status, "origin": "migration"},
        )
        return payment
