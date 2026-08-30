import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import (
    Estimate,
    EstimateCommercialSnapshotReference,
    EstimateJobConversion,
    EstimateLineItem,
    EstimateRevision,
)
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.invoicing.contracts import (
    AmountMutation,
    CreateFromEstimate,
    InvoiceMutation,
    PaymentApplication,
    PaymentReceiptFact,
    PostingReceiptFact,
)
from app.invoicing.errors import InvoiceConflict, InvoiceNotFound, InvoiceValidation
from app.invoicing.models import (
    AccountingPostingReceipt,
    ARLedgerEntry,
    Invoice,
    InvoiceIdempotency,
    InvoiceLine,
    InvoiceNumberSequence,
    PaymentReceiptEvidence,
)
from app.jobs.models import Job

CENT = Decimal("0.01")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class InvoiceService:
    async def create_from_estimate(
        self, session: AsyncSession, spec: CreateFromEstimate
    ) -> Invoice:
        request = _digest(
            {
                "operation": "create_from_estimate",
                "branch_id": spec.branch_id,
                "estimate_id": spec.estimate_id,
                "job_id": spec.job_id,
                "due_date": spec.due_date,
                "terms": spec.terms,
            }
        )
        async with session.begin():
            replay = await self._replay(
                session, spec.company_id, spec.idempotency_key, "create", request
            )
            if replay:
                return replay
            estimate = await session.scalar(
                select(Estimate)
                .where(
                    Estimate.company_id == spec.company_id,
                    Estimate.branch_id == spec.branch_id,
                    Estimate.id == spec.estimate_id,
                )
                .with_for_update()
            )
            if (
                estimate is None
                or estimate.current_revision_id is None
                or estimate.status not in {"approved", "accepted"}
                or estimate.acceptance_status not in {"approved", "accepted"}
            ):
                raise InvoiceNotFound("Accepted Estimate was not found.")
            replay = await self._replay(
                session, spec.company_id, spec.idempotency_key, "create", request
            )
            if replay:
                return replay
            existing_invoice = await session.scalar(
                select(Invoice).where(
                    Invoice.company_id == spec.company_id,
                    Invoice.estimate_revision_id == estimate.current_revision_id,
                )
            )
            if existing_invoice is not None:
                if (
                    existing_invoice.branch_id != spec.branch_id
                    or existing_invoice.job_id != spec.job_id
                    or existing_invoice.due_date != spec.due_date
                    or existing_invoice.terms != spec.terms.strip()
                ):
                    raise InvoiceConflict(
                        "Estimate revision already has contradictory Invoice authority."
                    )
                self._idempotency(
                    session,
                    existing_invoice,
                    spec.idempotency_key,
                    "create",
                    request,
                )
                return existing_invoice
            conversion = await session.scalar(
                select(EstimateJobConversion).where(
                    EstimateJobConversion.company_id == spec.company_id,
                    EstimateJobConversion.branch_id == spec.branch_id,
                    EstimateJobConversion.estimate_id == estimate.id,
                    EstimateJobConversion.estimate_revision_id
                    == estimate.current_revision_id,
                    EstimateJobConversion.job_id == spec.job_id,
                )
            )
            job = await session.scalar(
                select(Job).where(
                    Job.company_id == spec.company_id,
                    Job.branch_id == spec.branch_id,
                    Job.id == spec.job_id,
                    Job.customer_id == estimate.customer_id,
                    Job.service_location_id == estimate.service_location_id,
                    Job.status == "completed",
                )
            )
            if (
                conversion is None
                or job is None
                or estimate.service_location_id is None
            ):
                raise InvoiceNotFound("Completed accepted work was not found.")
            revision = await session.scalar(
                select(EstimateRevision).where(
                    EstimateRevision.company_id == spec.company_id,
                    EstimateRevision.id == estimate.current_revision_id,
                )
            )
            if revision is None:
                raise InvoiceNotFound("Accepted Estimate revision was not found.")
            if spec.due_date < datetime.now(timezone.utc).date():
                raise InvoiceValidation("Due date cannot precede the issue date.")
            rows = (
                await session.execute(
                    select(EstimateLineItem, EstimateCommercialSnapshotReference)
                    .join(
                        EstimateCommercialSnapshotReference,
                        (
                            EstimateCommercialSnapshotReference.company_id
                            == EstimateLineItem.company_id
                        )
                        & (
                            EstimateCommercialSnapshotReference.line_item_id
                            == EstimateLineItem.id
                        ),
                    )
                    .where(
                        EstimateLineItem.company_id == spec.company_id,
                        EstimateLineItem.revision_id == revision.id,
                    )
                    .order_by(EstimateLineItem.position)
                )
            ).all()
            if not rows:
                raise InvoiceValidation("Invoice requires authoritative line evidence.")
            invoice = Invoice(
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                customer_id=estimate.customer_id,
                service_location_id=estimate.service_location_id,
                job_id=job.id,
                estimate_id=estimate.id,
                estimate_revision_id=revision.id,
                invoice_number=await self._next_number(session, spec.company_id),
                identity_origin="native",
                status="draft",
                accounting_status="pending",
                currency=revision.currency,
                issue_date=datetime.now(timezone.utc).date(),
                due_date=spec.due_date,
                terms=spec.terms.strip(),
                subtotal_amount=revision.subtotal_amount,
                discount_amount=revision.discount_amount,
                taxable_basis=revision.taxable_basis,
                tax_amount=revision.tax_amount,
                total_amount=revision.total_amount,
                open_amount=Decimal("0.00"),
                calculation_digest=_digest(revision.calculation_evidence),
                legacy_evidence_missing=False,
                created_by_user_id=spec.actor_user_id,
                updated_by_user_id=spec.actor_user_id,
            )
            if not invoice.terms:
                raise InvoiceValidation("Invoice terms are required.")
            session.add(invoice)
            await session.flush()
            for line, ref in rows:
                session.add(
                    InvoiceLine(
                        company_id=spec.company_id,
                        invoice_id=invoice.id,
                        estimate_line_id=line.id,
                        snapshot_id=ref.snapshot_id,
                        snapshot_digest=ref.snapshot_digest,
                        position=line.position,
                        title=line.title,
                        description=line.description or line.title,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        line_total=line.line_total,
                        discount_allocation=line.discount_allocation,
                        discounted_basis=line.discounted_basis,
                        taxable=line.taxable,
                        tax_classification_id=line.tax_classification_id,
                        tax_policy_id=line.tax_policy_id,
                        tax_policy_version=line.tax_policy_version,
                        tax_rate_basis_points=line.applied_rate_basis_points,
                        tax_amount=line.tax_amount,
                        currency=line.currency,
                        evidence={"estimate_revision_id": str(revision.id)},
                    )
                )
            self._idempotency(session, invoice, spec.idempotency_key, "create", request)
            self._event(session, invoice, EventType.INVOICE_CREATED, spec.actor_user_id)
            await session.flush()
            return invoice

    async def issue(self, session: AsyncSession, spec: InvoiceMutation) -> Invoice:
        async with session.begin():
            invoice = await self._required(session, spec, lock=True)
            replay = await self._mutation_replay(session, invoice, spec, "issue")
            if replay:
                return invoice
            self._version(invoice, spec.expected_version)
            if invoice.status != "draft" or invoice.total_amount <= 0:
                raise InvoiceConflict("Invoice cannot be issued in its current state.")
            invoice.status = "issued"
            invoice.open_amount = invoice.total_amount
            invoice.issued_at = spec.occurred_at
            self._advance(invoice, spec.actor_user_id)
            self._ar(session, invoice, "obligation", invoice.total_amount, spec)
            self._event(session, invoice, EventType.INVOICE_ISSUED, spec.actor_user_id)
            return invoice

    async def credit(self, session: AsyncSession, spec: AmountMutation) -> Invoice:
        return await self._reduction(
            session, spec, "credit_memo", EventType.INVOICE_CREDIT_MEMO_ISSUED
        )

    async def write_off(self, session: AsyncSession, spec: AmountMutation) -> Invoice:
        return await self._reduction(
            session, spec, "write_off", EventType.INVOICE_WRITE_OFF_RECORDED
        )

    async def void(self, session: AsyncSession, spec: InvoiceMutation) -> Invoice:
        async with session.begin():
            invoice = await self._required(session, spec, lock=True)
            if await self._mutation_replay(session, invoice, spec, "void"):
                return invoice
            self._version(invoice, spec.expected_version)
            applied = await session.scalar(
                select(func.coalesce(func.sum(ARLedgerEntry.amount), 0)).where(
                    ARLedgerEntry.company_id == invoice.company_id,
                    ARLedgerEntry.invoice_id == invoice.id,
                    ARLedgerEntry.entry_type.in_(
                        ("payment_application", "application_reversal")
                    ),
                )
            )
            if (
                invoice.status not in {"issued", "adjusted"}
                or (applied or Decimal(0)) != 0
            ):
                raise InvoiceConflict("Only an unpaid issued Invoice can be voided.")
            amount = invoice.open_amount
            invoice.open_amount = Decimal("0.00")
            invoice.status = "voided"
            self._advance(invoice, spec.actor_user_id)
            self._ar(session, invoice, "void", -amount, spec)
            self._event(session, invoice, EventType.INVOICE_VOIDED, spec.actor_user_id)
            return invoice

    async def register_payment_receipt(
        self, session: AsyncSession, fact: PaymentReceiptFact
    ) -> PaymentReceiptEvidence:
        async with session.begin():
            if session.get_bind().dialect.name == "postgresql":
                await session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"
                    ),
                    {
                        "identity": (
                            f"invoice-payment-receipt:{fact.company_id}:"
                            f"{fact.receipt_id}"
                        )
                    },
                )
            existing = await session.scalar(
                select(PaymentReceiptEvidence).where(
                    PaymentReceiptEvidence.company_id == fact.company_id,
                    PaymentReceiptEvidence.receipt_id == fact.receipt_id,
                )
            )
            if existing:
                existing_authority = (
                    existing.branch_id,
                    existing.customer_id,
                    existing.currency,
                    existing.verified_amount,
                    existing.occurred_at,
                    existing.evidence_digest,
                )
                requested_authority = (
                    fact.branch_id,
                    fact.customer_id,
                    fact.currency,
                    fact.verified_amount,
                    fact.occurred_at,
                    fact.evidence_digest,
                )
                if existing_authority != requested_authority:
                    raise InvoiceConflict(
                        "Payment receipt evidence conflicts with replay."
                    )
                return existing
            if fact.verified_amount <= 0 or len(fact.evidence_digest) != 64:
                raise InvoiceValidation("Verified payment evidence is invalid.")
            evidence = PaymentReceiptEvidence(
                **asdict(fact), available_amount=fact.verified_amount
            )
            session.add(evidence)
            await session.flush()
            return evidence

    async def apply_payment(
        self, session: AsyncSession, spec: PaymentApplication
    ) -> Invoice:
        async with session.begin():
            invoice = await self._required(session, spec, lock=True)
            if await self._mutation_replay(session, invoice, spec, "apply_payment"):
                return invoice
            self._version(invoice, spec.expected_version)
            receipt = await session.scalar(
                select(PaymentReceiptEvidence)
                .where(
                    PaymentReceiptEvidence.company_id == spec.company_id,
                    PaymentReceiptEvidence.branch_id == spec.branch_id,
                    PaymentReceiptEvidence.customer_id == invoice.customer_id,
                    PaymentReceiptEvidence.receipt_id == spec.receipt_id,
                    PaymentReceiptEvidence.currency == invoice.currency,
                )
                .with_for_update()
            )
            if receipt is None:
                raise InvoiceNotFound("Verified payment receipt was not found.")
            amount = spec.amount.quantize(CENT)
            if (
                amount <= 0
                or amount > receipt.available_amount
                or amount > invoice.open_amount
            ):
                raise InvoiceConflict(
                    "Payment application exceeds an available balance."
                )
            receipt.available_amount -= amount
            invoice.open_amount -= amount
            invoice.status = "paid" if invoice.open_amount == 0 else "partially_paid"
            self._advance(invoice, spec.actor_user_id)
            self._ar(
                session,
                invoice,
                "payment_application",
                -amount,
                spec,
                source_id=receipt.receipt_id,
            )
            self._event(
                session, invoice, EventType.INVOICE_PAYMENT_APPLIED, spec.actor_user_id
            )
            return invoice

    async def reverse_payment_application(
        self, session: AsyncSession, spec: PaymentApplication
    ) -> Invoice:
        async with session.begin():
            invoice = await self._required(session, spec, lock=True)
            if await self._mutation_replay(
                session, invoice, spec, "reverse_payment_application"
            ):
                return invoice
            self._version(invoice, spec.expected_version)
            receipt = await session.scalar(
                select(PaymentReceiptEvidence)
                .where(
                    PaymentReceiptEvidence.company_id == spec.company_id,
                    PaymentReceiptEvidence.branch_id == spec.branch_id,
                    PaymentReceiptEvidence.customer_id == invoice.customer_id,
                    PaymentReceiptEvidence.receipt_id == spec.receipt_id,
                    PaymentReceiptEvidence.currency == invoice.currency,
                )
                .with_for_update()
            )
            applied = await session.scalar(
                select(func.coalesce(func.sum(ARLedgerEntry.amount), 0)).where(
                    ARLedgerEntry.company_id == spec.company_id,
                    ARLedgerEntry.invoice_id == invoice.id,
                    ARLedgerEntry.source_id == spec.receipt_id,
                    ARLedgerEntry.entry_type.in_(
                        ("payment_application", "application_reversal")
                    ),
                )
            )
            amount = spec.amount.quantize(CENT)
            if receipt is None or amount <= 0 or amount > -(applied or Decimal(0)):
                raise InvoiceConflict("Payment reversal exceeds applied evidence.")
            receipt.available_amount += amount
            invoice.open_amount += amount
            invoice.status = (
                "issued"
                if invoice.open_amount == invoice.total_amount
                else "partially_paid"
            )
            self._advance(invoice, spec.actor_user_id)
            self._ar(
                session,
                invoice,
                "application_reversal",
                amount,
                spec,
                source_id=receipt.receipt_id,
            )
            self._event(
                session,
                invoice,
                EventType.INVOICE_PAYMENT_APPLICATION_REVERSED,
                spec.actor_user_id,
            )
            return invoice

    async def record_posting_receipt(
        self, session: AsyncSession, fact: PostingReceiptFact
    ) -> Invoice:
        async with session.begin():
            invoice = await session.scalar(
                select(Invoice)
                .where(
                    Invoice.company_id == fact.company_id,
                    Invoice.branch_id == fact.branch_id,
                    Invoice.id == fact.invoice_id,
                )
                .with_for_update()
            )
            if invoice is None:
                raise InvoiceNotFound("Invoice was not found.")
            source_event = await session.scalar(
                select(BusinessEvent).where(
                    BusinessEvent.id == fact.source_event_id,
                    BusinessEvent.company_id == fact.company_id,
                    BusinessEvent.branch_id == fact.branch_id,
                    BusinessEvent.entity_type == "invoice",
                    BusinessEvent.entity_id == fact.invoice_id,
                )
            )
            if source_event is None:
                raise InvoiceConflict(
                    "Accounting receipt source is not authoritative invoice evidence."
                )
            existing = await session.scalar(
                select(AccountingPostingReceipt).where(
                    AccountingPostingReceipt.company_id == fact.company_id,
                    AccountingPostingReceipt.source_event_id == fact.source_event_id,
                )
            )
            if existing:
                existing_authority = (
                    existing.invoice_id,
                    existing.journal_id,
                    existing.journal_version,
                    existing.policy_version,
                    existing.status,
                    existing.effective_date,
                    existing.posted_at,
                )
                requested_authority = (
                    fact.invoice_id,
                    fact.journal_id,
                    fact.journal_version,
                    fact.policy_version,
                    fact.status,
                    fact.effective_date,
                    fact.posted_at,
                )
                if existing_authority != requested_authority:
                    raise InvoiceConflict("Accounting receipt conflicts with replay.")
                return invoice
            session.add(AccountingPostingReceipt(**asdict(fact)))
            invoice.accounting_status = fact.status
            invoice.version += 1
            invoice.updated_at = fact.posted_at
            await session.flush()
            return invoice

    async def get(
        self, session: AsyncSession, company_id: UUID, invoice_id: UUID
    ) -> Invoice | None:
        return await session.scalar(
            select(Invoice).where(
                Invoice.company_id == company_id, Invoice.id == invoice_id
            )
        )

    async def list(
        self, session: AsyncSession, company_id: UUID, branches: frozenset[UUID]
    ) -> tuple[Invoice, ...]:
        return tuple(
            (
                await session.scalars(
                    select(Invoice)
                    .where(
                        Invoice.company_id == company_id,
                        Invoice.branch_id.in_(branches),
                    )
                    .order_by(Invoice.created_at.desc(), Invoice.id)
                )
            ).all()
        )

    async def _reduction(self, session, spec, kind, event):
        async with session.begin():
            invoice = await self._required(session, spec, lock=True)
            if await self._mutation_replay(session, invoice, spec, kind):
                return invoice
            self._version(invoice, spec.expected_version)
            amount = spec.amount.quantize(CENT)
            if (
                invoice.status not in {"issued", "partially_paid", "adjusted"}
                or amount <= 0
                or amount > invoice.open_amount
                or not spec.reason_code.strip()
            ):
                raise InvoiceConflict("Adjustment exceeds the open Invoice balance.")
            invoice.open_amount -= amount
            invoice.status = "paid" if invoice.open_amount == 0 else "adjusted"
            self._advance(invoice, spec.actor_user_id)
            self._ar(session, invoice, kind, -amount, spec)
            self._event(session, invoice, event, spec.actor_user_id)
            return invoice

    @staticmethod
    async def _next_number(session, company_id):
        value = await session.scalar(
            insert(InvoiceNumberSequence)
            .values(company_id=company_id, last_value=1)
            .on_conflict_do_update(
                index_elements=[InvoiceNumberSequence.company_id],
                set_={
                    "last_value": InvoiceNumberSequence.last_value + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(InvoiceNumberSequence.last_value)
        )
        return f"INV-{value:06d}"

    @staticmethod
    async def _required(session, spec, lock=False):
        stmt = select(Invoice).where(
            Invoice.company_id == spec.company_id,
            Invoice.branch_id == spec.branch_id,
            Invoice.id == spec.invoice_id,
        )
        invoice = await session.scalar(stmt.with_for_update() if lock else stmt)
        if invoice is None:
            raise InvoiceNotFound("Invoice was not found.")
        return invoice

    async def _replay(self, session, company_id, key, operation, request_digest):
        existing = await session.scalar(
            select(InvoiceIdempotency).where(
                InvoiceIdempotency.company_id == company_id,
                InvoiceIdempotency.idempotency_key == key,
            )
        )
        if existing is None:
            return None
        if existing.operation != operation or existing.request_digest != request_digest:
            raise InvoiceConflict("Idempotency key conflicts with prior evidence.")
        return await session.scalar(
            select(Invoice).where(
                Invoice.company_id == company_id, Invoice.id == existing.invoice_id
            )
        )

    async def _mutation_replay(self, session, invoice, spec, operation):
        request = _digest(
            {
                "operation": operation,
                **{
                    k: v
                    for k, v in asdict(spec).items()
                    if k not in {"expected_version", "actor_user_id", "occurred_at"}
                },
            }
        )
        replay = await self._replay(
            session, spec.company_id, spec.idempotency_key, operation, request
        )
        if replay:
            return True
        self._idempotency(session, invoice, spec.idempotency_key, operation, request)
        return False

    @staticmethod
    def _idempotency(session, invoice, key, operation, request):
        session.add(
            InvoiceIdempotency(
                company_id=invoice.company_id,
                idempotency_key=key,
                operation=operation,
                request_digest=request,
                invoice_id=invoice.id,
            )
        )

    @staticmethod
    def _version(invoice, expected):
        if invoice.version != expected:
            raise InvoiceConflict("Invoice version is stale.")

    @staticmethod
    def _advance(invoice, actor):
        invoice.version += 1
        invoice.updated_by_user_id = actor
        invoice.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _ar(session, invoice, kind, amount, spec, source_id=None):
        session.add(
            ARLedgerEntry(
                company_id=invoice.company_id,
                branch_id=invoice.branch_id,
                customer_id=invoice.customer_id,
                invoice_id=invoice.id,
                entry_type=kind,
                amount=amount,
                currency=invoice.currency,
                source_id=source_id or invoice.id,
                source_version=invoice.version,
                reason_code=getattr(spec, "reason_code", None),
                idempotency_key=spec.idempotency_key,
                actor_user_id=spec.actor_user_id,
                occurred_at=spec.occurred_at,
            )
        )

    @staticmethod
    def _event(session, invoice, event, actor):
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event,
                entity_type="invoice",
                entity_id=invoice.id,
                company_id=invoice.company_id,
                branch_id=invoice.branch_id,
                user_id=actor,
                payload={
                    "schema_version": 1,
                    "invoice_id": str(invoice.id),
                    "customer_id": str(invoice.customer_id),
                    "currency": invoice.currency,
                    "subtotal": str(invoice.subtotal_amount),
                    "discount": str(invoice.discount_amount),
                    "tax": str(invoice.tax_amount),
                    "total": str(invoice.total_amount),
                    "open_amount": str(invoice.open_amount),
                    "source_version": invoice.version,
                    "calculation_digest": invoice.calculation_digest,
                },
            ),
        )


invoice_service = InvoiceService()
