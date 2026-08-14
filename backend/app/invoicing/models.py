from datetime import date, datetime, timezone
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.financials import models as financial_models

# The migration/import foundation owns the original Invoice table metadata. Replace
# only constraints whose definitions are deliberately evolved by Day-1 AR so
# metadata-based test schemas remain equivalent to the migrated schema.
_invoice_table = cast(Table, financial_models.Invoice.__table__)
for _constraint in tuple(_invoice_table.constraints):
    if _constraint.name in {
        "ck_invoices_status",
        "ck_invoices_amounts",
        "uq_invoices_company_id",
    }:
        _invoice_table.constraints.discard(_constraint)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvoiceNumberSequence(Base):
    __tablename__ = "invoice_number_sequences"
    __table_args__ = (CheckConstraint("last_value >= 0", name="ck_invoice_sequence"),)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_invoices_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_invoices_location_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_invoices_job",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_invoices_estimate",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(identity_origin = 'native' AND invoice_number ~ '^INV-[0-9]{6,}$') "
            "OR (identity_origin = 'grandfathered_legacy' "
            "AND legacy_evidence_missing = true)",
            name="ck_invoices_number",
        ),
        CheckConstraint(
            "identity_origin IN ('native','grandfathered_legacy')",
            name="ck_invoices_identity_origin",
        ),
        CheckConstraint(
            "status IN ('draft','cancelled','issued','partially_paid','adjusted','paid','voided')",
            name="ck_invoices_status",
        ),
        CheckConstraint(
            "accounting_status IN ('pending','posted','reversed','reconciliation_required')",
            name="ck_invoices_accounting_status",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_invoices_currency"),
        CheckConstraint("version >= 1", name="ck_invoices_version"),
        CheckConstraint(
            "subtotal_amount >= 0 AND discount_amount >= 0 AND taxable_basis >= 0 AND tax_amount >= 0 AND total_amount >= 0 AND open_amount >= 0",
            name="ck_invoices_amounts",
        ),
        CheckConstraint("due_date >= issue_date", name="ck_invoices_dates"),
        UniqueConstraint(
            "company_id", "invoice_number", name="uq_invoices_company_number"
        ),
        UniqueConstraint("company_id", "id", name="uq_invoices_company_id"),
        UniqueConstraint(
            "company_id", "estimate_revision_id", name="uq_invoices_estimate_revision"
        ),
        Index(
            "ix_invoices_company_branch_status_due",
            "company_id",
            "branch_id",
            "status",
            "due_date",
        ),
        Index(
            "ix_invoices_company_customer_due", "company_id", "customer_id", "due_date"
        ),
        {"extend_existing": True},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", name="fk_invoices_company", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    estimate_revision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    identity_origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="native", server_default="native"
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    accounting_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    terms: Mapped[str] = mapped_column(Text, nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    taxable_basis: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    open_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    calculation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_evidence_missing: Mapped[bool] = mapped_column(nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_invoices_updated_by", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_invoice_lines_invoice",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "position >= 1 AND quantity > 0 AND unit_price >= 0 AND total_amount >= 0",
            name="ck_invoice_lines_amounts",
        ),
        CheckConstraint(
            "discount_allocation >= 0 AND discounted_basis >= 0 AND tax_amount >= 0",
            name="ck_invoice_lines_calculations",
        ),
        UniqueConstraint(
            "company_id", "invoice_id", "position", name="uq_invoice_lines_position"
        ),
        {"extend_existing": True},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id", name="fk_invoice_lines_company", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    estimate_line_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    snapshot_digest: Mapped[str | None] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(
        "total_amount", Numeric(18, 2), nullable=False
    )
    discount_allocation: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    discounted_basis: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    taxable: Mapped[bool | None] = mapped_column()
    tax_classification_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_policy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    tax_policy_version: Mapped[int | None] = mapped_column(Integer)
    tax_rate_basis_points: Mapped[int | None] = mapped_column(Integer)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ARLedgerEntry(Base):
    __tablename__ = "ar_ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_ar_entries_invoice",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_ar_entries_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "entry_type IN ('obligation','credit_memo','write_off','void','payment_application','application_reversal','write_off_reversal')",
            name="ck_ar_entries_type",
        ),
        CheckConstraint("amount <> 0", name="ck_ar_entries_amount"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_ar_entries_idempotency"
        ),
        Index(
            "ix_ar_entries_invoice_time",
            "company_id",
            "invoice_id",
            "occurred_at",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class InvoiceIdempotency(Base):
    __tablename__ = "invoice_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_invoice_idempotency_key"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PaymentReceiptEvidence(Base):
    __tablename__ = "invoice_payment_receipt_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_invoice_receipts_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "verified_amount > 0 AND available_amount >= 0 AND available_amount <= verified_amount",
            name="ck_invoice_receipts_amount",
        ),
        UniqueConstraint("company_id", "receipt_id", name="uq_invoice_receipts_source"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    verified_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    available_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AccountingPostingReceipt(Base):
    __tablename__ = "invoice_accounting_posting_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_invoice_posting_receipts_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_invoice_posting_receipts_invoice",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('posted','reversed','reconciliation_required')",
            name="ck_invoice_posting_receipts_status",
        ),
        UniqueConstraint(
            "company_id", "source_event_id", name="uq_invoice_posting_receipts_event"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
