from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["company_id", "customer_id"],
            ["customers.company_id", "customers.id"],
            name="fk_payment_intents_customer_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "invoice_id", "customer_id"],
            ["invoices.company_id", "invoices.branch_id", "invoices.id", "invoices.customer_id"],
            name="fk_payment_intents_invoice_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "amount > 0 AND currency ~ '^[A-Z]{3}$'",
            name="payment_intents_check",
        ),
        CheckConstraint(
            "status IN ('created','requires_action','authorized','captured','declined','failed','cancelled','expired','reconciliation_required')",
            name="payment_intents_status_check",
        ),
        UniqueConstraint("company_id", "idempotency_key"),
        UniqueConstraint("company_id", "provider_idempotency_key"),
        UniqueConstraint("company_id", "id"),
        Index("ix_payment_intents_scope", "company_id", "branch_id", "customer_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant_account: Mapped[str] = mapped_column(String(120), nullable=False)
    opaque_payment_method: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_operation_id: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (ForeignKeyConstraint(["company_id", "intent_id"], ["payment_intents.company_id", "payment_intents.id"], ondelete="RESTRICT"), UniqueConstraint("company_id", "intent_id", "sequence"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    intent_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(24), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_operation_id: Mapped[str | None] = mapped_column(String(255))
    provider_code: Mapped[str | None] = mapped_column(String(80))
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PaymentReceipt(Base):
    __tablename__ = "payment_receipts"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "intent_id"], ["payment_intents.company_id", "payment_intents.id"], ondelete="RESTRICT"),
        CheckConstraint(
            "captured_amount >= 0 AND available_amount >= 0 AND applied_amount >= 0 AND refunded_amount >= 0 AND disputed_amount >= 0",
            name="payment_receipts_check",
        ),
        CheckConstraint(
            "captured_amount = available_amount + applied_amount + refunded_amount + disputed_amount",
            name="payment_receipts_check1",
        ),
        UniqueConstraint("company_id", "intent_id"), UniqueConstraint("company_id", "id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    intent_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unapplied")
    captured_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    available_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    applied_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    disputed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReceiptEvent(Base):
    __tablename__ = "payment_receipt_events"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "receipt_id"], ["payment_receipts.company_id", "payment_receipts.id"], ondelete="RESTRICT"),
        CheckConstraint(
            "event_type <> 'dispute_recorded' OR "
            "(provider_reference IS NOT NULL AND length(btrim(provider_reference)) > 0 "
            "AND request_digest IS NOT NULL AND length(request_digest) = 64)",
            name="ck_payment_receipt_events_dispute_evidence",
        ),
        UniqueConstraint("company_id", "receipt_id", "idempotency_key"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    external_identity: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Refund(Base):
    __tablename__ = "payment_refunds"
    __table_args__ = (ForeignKeyConstraint(["company_id", "receipt_id"], ["payment_receipts.company_id", "payment_receipts.id"], ondelete="RESTRICT"), CheckConstraint("amount > 0", name="payment_refunds_amount_check"), UniqueConstraint("company_id", "idempotency_key"), UniqueConstraint("company_id", "id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_operation_id: Mapped[str | None] = mapped_column(String(255))
    evidence_digest: Mapped[str | None] = mapped_column(String(64))
    requested_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Deposit(Base):
    __tablename__ = "payment_deposits"
    __table_args__ = (CheckConstraint("gross_amount >= 0", name="payment_deposits_gross_amount_check"), UniqueConstraint("company_id", "idempotency_key"), UniqueConstraint("company_id", "id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    destination_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    prepared_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DepositReceipt(Base):
    __tablename__ = "payment_deposit_receipts"
    __table_args__ = (ForeignKeyConstraint(["company_id", "deposit_id"], ["payment_deposits.company_id", "payment_deposits.id"], ondelete="RESTRICT"), ForeignKeyConstraint(["company_id", "receipt_id"], ["payment_receipts.company_id", "payment_receipts.id"], ondelete="RESTRICT"), UniqueConstraint("company_id", "receipt_id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    deposit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class Settlement(Base):
    __tablename__ = "payment_settlements"
    __table_args__ = (CheckConstraint("gross_amount - refund_amount - dispute_amount - fee_amount + adjustment_amount = net_amount", name="payment_settlements_check"), UniqueConstraint("company_id", "provider", "merchant_account", "provider_payout_id"), UniqueConstraint("company_id", "id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant_account: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_payout_id: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    dispute_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReconciliationException(Base):
    __tablename__ = "payment_reconciliation_exceptions"
    __table_args__ = (UniqueConstraint("company_id", "idempotency_key"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    opened_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookReceipt(Base):
    __tablename__ = "payment_webhook_receipts"
    __table_args__ = (UniqueConstraint("company_id", "provider", "merchant_account", "provider_event_id"), UniqueConstraint("company_id", "evidence_digest"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant_account: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_version: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_evidence: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PaymentPostingReceipt(Base):
    __tablename__ = "payment_accounting_posting_receipts"
    __table_args__ = (UniqueConstraint("company_id", "source_event_id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
