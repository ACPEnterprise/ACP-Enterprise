import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.invoicing.contracts import PaymentApplication, PaymentReceiptFact
from app.invoicing.errors import InvoiceError
from app.invoicing.service import invoice_service
from app.payments.contracts import (
    ApplyReceipt,
    CreateDeposit,
    CreateIntent,
    PaymentProvider,
    PostingReceiptFact,
    ProviderRequest,
    RecordDispute,
    RecordSettlement,
    RequestRefund,
    VerifiedWebhook,
)
from app.payments.errors import PaymentConflict, PaymentNotFound, PaymentValidation
from app.payments.models import (
    Deposit,
    DepositReceipt,
    PaymentAttempt,
    PaymentIntent,
    PaymentPostingReceipt,
    PaymentReceipt,
    ReceiptEvent,
    ReconciliationException,
    Refund,
    Settlement,
    WebhookReceipt,
)
from app.payments.provider import DeterministicFakeProvider

CENT = Decimal("0.01")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class PaymentService:
    def __init__(self, provider: PaymentProvider, merchant_account: str) -> None:
        self.provider = provider
        self.merchant_account = merchant_account

    async def collect(self, session: AsyncSession, spec: CreateIntent) -> PaymentIntent:
        amount = spec.amount.quantize(CENT)
        request_digest = _digest({"operation": "collect", "branch_id": spec.branch_id, "customer_id": spec.customer_id, "invoice_id": spec.invoice_id, "amount": amount, "currency": spec.currency, "opaque_payment_method": spec.opaque_payment_method})
        async with session.begin():
            await self._lock_command(
                session, spec.company_id, "collect", spec.idempotency_key
            )
            existing = await session.scalar(select(PaymentIntent).where(PaymentIntent.company_id == spec.company_id, PaymentIntent.idempotency_key == spec.idempotency_key).with_for_update())
            if existing:
                if existing.request_digest != request_digest:
                    raise PaymentConflict("Idempotency key conflicts with the original request.")
                return existing
            if amount <= 0 or len(spec.currency) != 3 or not spec.opaque_payment_method.startswith("opaque_"):
                raise PaymentValidation("Positive amount, ISO currency, and provider-safe opaque identity are required.")
            intent = PaymentIntent(company_id=spec.company_id, branch_id=spec.branch_id, customer_id=spec.customer_id, invoice_id=spec.invoice_id, amount=amount, currency=spec.currency.upper(), provider=self.provider.name, merchant_account=self.merchant_account, opaque_payment_method=spec.opaque_payment_method, idempotency_key=spec.idempotency_key, request_digest=request_digest, provider_idempotency_key=f"pay_{uuid4().hex}", created_by_user_id=spec.actor_user_id)
            session.add(intent)
            await session.flush()
            self._event(session, intent, EventType.PAYMENT_INTENT_CREATED, spec.actor_user_id)

        result = await self.provider.collect(ProviderRequest(intent.id, intent.provider_idempotency_key, self.merchant_account, amount, intent.currency, spec.opaque_payment_method))
        receipt: PaymentReceipt | None = None
        async with session.begin():
            locked_intent = await session.scalar(select(PaymentIntent).where(PaymentIntent.company_id == spec.company_id, PaymentIntent.id == intent.id).with_for_update())
            assert locked_intent is not None
            intent = locked_intent
            if intent.status != "created":
                return intent
            intent.provider_operation_id = result.provider_operation_id
            intent.status = "reconciliation_required" if result.outcome == "ambiguous" else result.outcome
            intent.version += 1
            intent.updated_at = datetime.now(timezone.utc)
            session.add(PaymentAttempt(company_id=intent.company_id, intent_id=intent.id, sequence=1, operation="capture", outcome=result.outcome, provider_operation_id=result.provider_operation_id, provider_code=result.provider_code, evidence_digest=result.evidence_digest))
            if result.outcome == "captured":
                receipt = PaymentReceipt(company_id=intent.company_id, branch_id=intent.branch_id, customer_id=intent.customer_id, intent_id=intent.id, currency=intent.currency, status="unapplied", captured_amount=amount, available_amount=amount, applied_amount=0, refunded_amount=0, disputed_amount=0, evidence_digest=result.evidence_digest)
                session.add(receipt)
                await session.flush()
                self._event(session, receipt, EventType.PAYMENT_RECEIPT_CAPTURED, spec.actor_user_id)
            elif result.outcome == "ambiguous":
                self._exception(session, intent, "ambiguous_processor_outcome", result.evidence_digest, spec.actor_user_id)
            else:
                self._event(session, intent, EventType.PAYMENT_FAILED, spec.actor_user_id)
        if receipt:
            await invoice_service.register_payment_receipt(session, PaymentReceiptFact(company_id=receipt.company_id, branch_id=receipt.branch_id, customer_id=receipt.customer_id, receipt_id=receipt.id, currency=receipt.currency, verified_amount=receipt.captured_amount, occurred_at=receipt.captured_at, evidence_digest=receipt.evidence_digest))
        return intent

    async def apply(self, session: AsyncSession, spec: ApplyReceipt) -> PaymentReceipt:
        amount = spec.amount.quantize(CENT)
        digest = _digest({"invoice_id": spec.invoice_id, "amount": amount, "expected_invoice_version": spec.expected_invoice_version})
        async with session.begin():
            receipt = await self._receipt(session, spec.company_id, spec.branch_id, spec.receipt_id, True)
            prior = await session.scalar(select(ReceiptEvent).where(ReceiptEvent.company_id == spec.company_id, ReceiptEvent.receipt_id == spec.receipt_id, ReceiptEvent.idempotency_key == spec.idempotency_key))
            if prior:
                if prior.evidence_digest != digest:
                    raise PaymentConflict("Idempotency key conflicts with the original application.")
                return receipt
            if amount <= 0 or amount > receipt.available_amount:
                raise PaymentConflict("Application exceeds receipt availability.")
        try:
            invoice = await invoice_service.apply_payment(session, PaymentApplication(company_id=spec.company_id, branch_id=spec.branch_id, invoice_id=spec.invoice_id, receipt_id=spec.receipt_id, amount=amount, expected_version=spec.expected_invoice_version, actor_user_id=spec.actor_user_id, idempotency_key=spec.idempotency_key, occurred_at=spec.occurred_at))
        except InvoiceError as exc:
            raise PaymentConflict(str(exc)) from exc
        async with session.begin():
            receipt = await self._receipt(session, spec.company_id, spec.branch_id, spec.receipt_id, True)
            receipt.available_amount -= amount
            receipt.applied_amount += amount
            receipt.status = "fully_applied" if receipt.available_amount == 0 else "partially_applied"
            receipt.version += 1
            session.add(ReceiptEvent(company_id=spec.company_id, receipt_id=receipt.id, event_type="application_observed", amount=amount, invoice_id=invoice.id, idempotency_key=spec.idempotency_key, evidence_digest=digest))
        return receipt

    async def request_refund(self, session: AsyncSession, spec: RequestRefund) -> Refund:
        amount = spec.amount.quantize(CENT)
        digest = _digest({"receipt_id": spec.receipt_id, "amount": amount, "reason": spec.reason.strip()})
        async with session.begin():
            await self._lock_command(
                session, spec.company_id, "refund", spec.idempotency_key
            )
            prior = await session.scalar(select(Refund).where(Refund.company_id == spec.company_id, Refund.idempotency_key == spec.idempotency_key))
            if prior:
                if prior.request_digest != digest:
                    raise PaymentConflict("Idempotency key conflicts with the original refund.")
                return prior
            receipt = await self._receipt(session, spec.company_id, spec.branch_id, spec.receipt_id, True)
            if receipt.version != spec.expected_version or amount <= 0 or amount > receipt.available_amount or not spec.reason.strip():
                raise PaymentConflict("Refund is stale or exceeds unapplied refundable balance.")
            refund = Refund(company_id=spec.company_id, branch_id=spec.branch_id, receipt_id=receipt.id, amount=amount, currency=receipt.currency, reason=spec.reason.strip(), idempotency_key=spec.idempotency_key, request_digest=digest, requested_by_user_id=spec.actor_user_id)
            session.add(refund)
            await session.flush()
            self._event(session, refund, EventType.PAYMENT_REFUND_REQUESTED, spec.actor_user_id)
        result = await self.provider.refund(ProviderRequest(refund.id, f"refund_{refund.id.hex}", self.merchant_account, amount, refund.currency, "opaque_refund"))
        async with session.begin():
            locked_refund = await session.scalar(select(Refund).where(Refund.company_id == spec.company_id, Refund.id == refund.id).with_for_update())
            receipt = await self._receipt(session, spec.company_id, spec.branch_id, spec.receipt_id, True)
            assert locked_refund is not None
            refund = locked_refund
            refund.provider_operation_id = result.provider_operation_id
            refund.evidence_digest = result.evidence_digest
            refund.status = "reconciliation_required" if result.outcome == "ambiguous" else ("succeeded" if result.outcome == "captured" else "failed")
            if refund.status == "succeeded":
                receipt.available_amount -= amount
                receipt.refunded_amount += amount
                receipt.status = "refunded" if receipt.refunded_amount == receipt.captured_amount else "partially_refunded"
                receipt.version += 1
                session.add(ReceiptEvent(company_id=spec.company_id, receipt_id=receipt.id, event_type="refund_succeeded", amount=amount, external_identity=refund.id, idempotency_key=spec.idempotency_key, evidence_digest=result.evidence_digest))
                self._event(session, refund, EventType.PAYMENT_REFUND_SUCCEEDED, spec.actor_user_id)
            elif refund.status == "failed":
                self._event(session, refund, EventType.PAYMENT_REFUND_FAILED, spec.actor_user_id)
            else:
                self._exception(session, refund, "ambiguous_refund_outcome", result.evidence_digest, spec.actor_user_id)
        return refund

    async def record_webhook(self, session: AsyncSession, company_id: UUID, provider: str, evidence: VerifiedWebhook) -> WebhookReceipt:
        async with session.begin():
            await self._lock_command(
                session,
                company_id,
                "webhook",
                f"{provider}:{evidence.merchant_account}:{evidence.provider_event_id}",
            )
            prior = await session.scalar(select(WebhookReceipt).where(WebhookReceipt.company_id == company_id, WebhookReceipt.provider == provider, WebhookReceipt.merchant_account == evidence.merchant_account, WebhookReceipt.provider_event_id == evidence.provider_event_id))
            if prior:
                if prior.evidence_digest != evidence.evidence_digest:
                    self._exception_raw(session, company_id, "webhook", prior.id, "contradictory_provider_event", evidence.evidence_digest)
                    raise PaymentConflict("Provider event identity conflicts with prior evidence.")
                return prior
            row = WebhookReceipt(company_id=company_id, provider=provider, merchant_account=evidence.merchant_account, provider_event_id=evidence.provider_event_id, event_type=evidence.event_type, evidence_digest=evidence.evidence_digest, secret_version=evidence.secret_version, allowed_evidence=evidence.allowed_evidence)
            session.add(row)
            await session.flush()
            return row

    async def create_deposit(self, session: AsyncSession, spec: CreateDeposit) -> Deposit:
        digest = _digest({"receipt_ids": sorted(str(value) for value in spec.receipt_ids), "currency": spec.currency, "destination_reference": spec.destination_reference})
        async with session.begin():
            await self._lock_command(
                session, spec.company_id, "deposit", spec.idempotency_key
            )
            prior = await session.scalar(select(Deposit).where(Deposit.company_id == spec.company_id, Deposit.idempotency_key == spec.idempotency_key))
            if prior:
                if prior.evidence_digest != digest:
                    raise PaymentConflict("Idempotency key conflicts with the original deposit.")
                return prior
            if not spec.receipt_ids or not spec.destination_reference.strip():
                raise PaymentValidation("Deposit requires receipts and a destination reference.")
            rows = tuple((await session.scalars(select(PaymentReceipt).where(PaymentReceipt.company_id == spec.company_id, PaymentReceipt.branch_id == spec.branch_id, PaymentReceipt.id.in_(spec.receipt_ids), PaymentReceipt.currency == spec.currency).with_for_update())).all())
            if len(rows) != len(set(spec.receipt_ids)):
                raise PaymentNotFound("Eligible payment receipt was not found.")
            deposit = Deposit(company_id=spec.company_id, branch_id=spec.branch_id, currency=spec.currency, status="submitted", gross_amount=sum((row.captured_amount for row in rows), Decimal(0)), destination_reference=spec.destination_reference.strip(), idempotency_key=spec.idempotency_key, evidence_digest=digest, prepared_by_user_id=spec.actor_user_id)
            session.add(deposit)
            await session.flush()
            for row in rows:
                session.add(DepositReceipt(company_id=spec.company_id, deposit_id=deposit.id, receipt_id=row.id, amount=row.captured_amount))
            self._event(session, deposit, EventType.PAYMENT_DEPOSIT_SUBMITTED, spec.actor_user_id)
            return deposit

    async def record_settlement(self, session: AsyncSession, spec: RecordSettlement) -> Settlement:
        expected = spec.gross_amount - spec.refund_amount - spec.dispute_amount - spec.fee_amount + spec.adjustment_amount
        async with session.begin():
            await self._lock_command(
                session,
                spec.company_id,
                "settlement",
                f"{spec.provider}:{spec.merchant_account}:{spec.provider_payout_id}",
            )
            prior = await session.scalar(select(Settlement).where(Settlement.company_id == spec.company_id, Settlement.provider == spec.provider, Settlement.merchant_account == spec.merchant_account, Settlement.provider_payout_id == spec.provider_payout_id))
            if prior:
                if prior.evidence_digest != spec.evidence_digest:
                    raise PaymentConflict("Settlement evidence conflicts with replay.")
                return prior
            if spec.merchant_account != self.merchant_account or spec.provider != self.provider.name or len(spec.evidence_digest) != 64:
                raise PaymentValidation("Settlement provider scope or evidence is invalid.")
            status = "received" if expected == spec.net_amount else "reconciliation_required"
            row = Settlement(**{key: value for key, value in asdict(spec).items() if key != "actor_user_id"}, status=status)
            session.add(row)
            await session.flush()
            self._event(session, row, EventType.PAYMENT_SETTLEMENT_RECEIVED, spec.actor_user_id)
            if status == "reconciliation_required":
                self._exception_raw(session, spec.company_id, "settlement", row.id, "settlement_variance", spec.evidence_digest, actor=spec.actor_user_id)
            return row

    async def record_dispute(self, session: AsyncSession, spec: RecordDispute) -> PaymentReceipt:
        amount = spec.amount.quantize(CENT)
        async with session.begin():
            receipt = await self._receipt(session, spec.company_id, spec.branch_id, spec.receipt_id, True)
            prior = await session.scalar(select(ReceiptEvent).where(ReceiptEvent.company_id == spec.company_id, ReceiptEvent.receipt_id == receipt.id, ReceiptEvent.idempotency_key == spec.idempotency_key))
            if prior:
                return receipt
            if receipt.version != spec.expected_version or amount <= 0 or amount > receipt.available_amount or len(spec.evidence_digest) != 64:
                raise PaymentConflict("Dispute is stale or exceeds receipt availability.")
            receipt.available_amount -= amount
            receipt.disputed_amount += amount
            receipt.status = "disputed"
            receipt.version += 1
            session.add(ReceiptEvent(company_id=spec.company_id, receipt_id=receipt.id, event_type="dispute_recorded", amount=amount, idempotency_key=spec.idempotency_key, evidence_digest=spec.evidence_digest))
            self._event(session, receipt, EventType.PAYMENT_DISPUTE_RECORDED, spec.actor_user_id)
            return receipt

    async def record_posting_receipt(self, session: AsyncSession, fact: PostingReceiptFact) -> PaymentPostingReceipt:
        async with session.begin():
            await self._lock_command(
                session, fact.company_id, "posting", str(fact.source_event_id)
            )
            prior = await session.scalar(select(PaymentPostingReceipt).where(PaymentPostingReceipt.company_id == fact.company_id, PaymentPostingReceipt.source_event_id == fact.source_event_id))
            if prior:
                if prior.journal_id != fact.journal_id or prior.status != fact.status:
                    raise PaymentConflict("Accounting posting receipt conflicts with replay.")
                return prior
            row = PaymentPostingReceipt(**asdict(fact))
            session.add(row)
            await session.flush()
            return row

    async def list_receipts(self, session: AsyncSession, company_id: UUID, branches: frozenset[UUID]) -> tuple[PaymentReceipt, ...]:
        return tuple((await session.scalars(select(PaymentReceipt).where(PaymentReceipt.company_id == company_id, PaymentReceipt.branch_id.in_(branches)).order_by(PaymentReceipt.captured_at.desc()))).all())

    async def get_receipt(self, session: AsyncSession, company_id: UUID, receipt_id: UUID) -> PaymentReceipt | None:
        return await session.scalar(select(PaymentReceipt).where(PaymentReceipt.company_id == company_id, PaymentReceipt.id == receipt_id))

    async def _receipt(self, session: AsyncSession, company_id: UUID, branch_id: UUID, receipt_id: UUID, lock: bool) -> PaymentReceipt:
        query = select(PaymentReceipt).where(PaymentReceipt.company_id == company_id, PaymentReceipt.branch_id == branch_id, PaymentReceipt.id == receipt_id)
        row = await session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise PaymentNotFound("Payment receipt was not found.")
        return row

    @staticmethod
    async def _lock_command(
        session: AsyncSession, company_id: UUID, operation: str, key: str
    ) -> None:
        if session.get_bind().dialect.name != "postgresql":
            return
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": f"payments:{company_id}:{operation}:{key}"},
        )

    @staticmethod
    def _event(session: AsyncSession, entity: Any, event_type: EventType, actor: UUID) -> None:
        BusinessEventService.stage(session, BusinessEventCreate(event_type=event_type, entity_type=entity.__class__.__name__.lower(), entity_id=entity.id, company_id=entity.company_id, branch_id=getattr(entity, "branch_id", None), user_id=actor, payload={"schema_version": "1.0", "evidence_digest": getattr(entity, "evidence_digest", None), "currency": getattr(entity, "currency", None), "amount": str(getattr(entity, "amount", getattr(entity, "captured_amount", "0.00")))}))

    @staticmethod
    def _exception(session: AsyncSession, entity: Any, reason: str, digest: str, actor: UUID) -> None:
        PaymentService._exception_raw(session, entity.company_id, entity.__class__.__name__.lower(), entity.id, reason, digest, getattr(entity, "branch_id", None), actor)

    @staticmethod
    def _exception_raw(session: AsyncSession, company_id: UUID, entity_type: str, entity_id: UUID, reason: str, digest: str, branch_id: UUID | None = None, actor: UUID | None = None) -> None:
        row = ReconciliationException(company_id=company_id, branch_id=branch_id, entity_type=entity_type, entity_id=entity_id, reason_code=reason, idempotency_key=f"{entity_type}:{entity_id}:{reason}", evidence_digest=digest, opened_by_user_id=actor)
        session.add(row)
        BusinessEventService.stage(session, BusinessEventCreate(event_type=EventType.PAYMENT_RECONCILIATION_EXCEPTION_OPENED, entity_type="payment_reconciliation_exception", entity_id=row.id, company_id=company_id, branch_id=branch_id, user_id=actor, payload={"schema_version": "1.0", "reason_code": reason, "evidence_digest": digest}))


payment_service = PaymentService(DeterministicFakeProvider(), "synthetic-not-activated")
