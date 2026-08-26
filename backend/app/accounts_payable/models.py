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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccountingVendor(Base):
    __tablename__ = "ap_vendors"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')", name="ck_ap_vendors_status"),
        CheckConstraint("length(btrim(code)) > 0 AND length(btrim(legal_name)) > 0 AND length(btrim(display_name)) > 0", name="ck_ap_vendors_names"),
        UniqueConstraint("company_id", "code", name="uq_ap_vendors_company_code"),
        UniqueConstraint("company_id", "id", name="uq_ap_vendors_company_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(240), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    default_terms: Mapped[str | None] = mapped_column(String(120))
    provenance: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VendorSourceMapping(Base):
    __tablename__ = "ap_vendor_source_mappings"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "vendor_id"], ["ap_vendors.company_id", "ap_vendors.id"], ondelete="RESTRICT"),
        UniqueConstraint("company_id", "source_system", "source_company_id", "source_vendor_id", name="uq_ap_vendor_source_identity"),
        UniqueConstraint("company_id", "vendor_id", "source_system", name="uq_ap_vendor_source_vendor"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_company_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_vendor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mapped_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    mapped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class APAccountMapping(Base):
    __tablename__ = "ap_account_mappings"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "account_id"], ["accounting_accounts.company_id", "accounting_accounts.id"], ondelete="RESTRICT"),
        CheckConstraint("classification IN ('expense','prepaid','fixed_asset','inventory_asset','tax','freight','discount','cash','clearing','other')", name="ck_ap_account_mappings_classification"),
        UniqueConstraint("company_id", "mapping_key", "effective_from", name="uq_ap_account_mapping_version"),
        UniqueConstraint("company_id", "id", name="uq_ap_account_mappings_company_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    mapping_key: Mapped[str] = mapped_column(String(120), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    approved_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class VendorBill(Base):
    __tablename__ = "ap_bills"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "vendor_id"], ["ap_vendors.company_id", "ap_vendors.id"], ondelete="RESTRICT"),
        CheckConstraint("status IN ('draft','submitted','approved','posted','rejected','cancelled','partially_paid','paid','credited','reversed')", name="ck_ap_bills_status"),
        CheckConstraint("accounting_status IN ('pending','posted','reversed','reconciliation_required')", name="ck_ap_bills_accounting_status"),
        CheckConstraint("currency ~ '^[A-Z]{3}$' AND total_amount >= 0 AND open_amount >= 0 AND open_amount <= total_amount", name="ck_ap_bills_amounts"),
        CheckConstraint("due_date >= bill_date", name="ck_ap_bills_dates"),
        UniqueConstraint("company_id", "bill_number", name="uq_ap_bills_company_number"),
        UniqueConstraint("company_id", "vendor_id", "normalized_document_number", name="uq_ap_bills_vendor_document"),
        UniqueConstraint("company_id", "source_system", "source_identity", name="uq_ap_bills_source_identity"),
        UniqueConstraint("company_id", "id", name="uq_ap_bills_company_id"),
        Index("ix_ap_bills_aging", "company_id", "vendor_id", "status", "due_date"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    bill_number: Mapped[str] = mapped_column(String(40), nullable=False)
    vendor_document_number: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_document_number: Mapped[str] = mapped_column(String(160), nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    terms_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    accounting_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    open_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prepared_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    replacement_for_bill_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BillRevision(Base):
    __tablename__ = "ap_bill_revisions"
    __table_args__ = (ForeignKeyConstraint(["company_id", "bill_id"], ["ap_bills.company_id", "ap_bills.id"], ondelete="RESTRICT"), UniqueConstraint("company_id", "bill_id", "revision", name="uq_ap_bill_revision"), UniqueConstraint("company_id", "id", name="uq_ap_bill_revisions_company_id"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    bill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BillLine(Base):
    __tablename__ = "ap_bill_lines"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "revision_id"], ["ap_bill_revisions.company_id", "ap_bill_revisions.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "mapping_id"], ["ap_account_mappings.company_id", "ap_account_mappings.id"], ondelete="RESTRICT"),
        CheckConstraint("position >= 1 AND quantity > 0 AND net_amount >= 0 AND tax_amount >= 0", name="ck_ap_bill_lines_amounts"),
        UniqueConstraint("company_id", "revision_id", "position", name="uq_ap_bill_line_position"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    mapping_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purchasing_reference: Mapped[str | None] = mapped_column(String(255))
    receipt_reference: Mapped[str | None] = mapped_column(String(255))


class DuplicateOverride(Base):
    __tablename__ = "ap_duplicate_overrides"
    __table_args__ = (ForeignKeyConstraint(["company_id", "bill_id"], ["ap_bills.company_id", "ap_bills.id"], ondelete="RESTRICT"), CheckConstraint("requester_user_id <> reviewer_user_id", name="ck_ap_duplicate_override_sod"), UniqueConstraint("company_id", "bill_id", name="uq_ap_duplicate_override_bill"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    bill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    duplicate_bill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    requester_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class VendorCredit(Base):
    __tablename__ = "ap_vendor_credits"
    __table_args__ = (ForeignKeyConstraint(["company_id", "vendor_id"], ["ap_vendors.company_id", "ap_vendors.id"], ondelete="RESTRICT"), CheckConstraint("amount > 0 AND available_amount >= 0 AND available_amount <= amount", name="ck_ap_vendor_credits_amounts"), UniqueConstraint("company_id", "credit_number", name="uq_ap_vendor_credit_number"), UniqueConstraint("company_id", "source_system", "source_identity", name="uq_ap_vendor_credit_source"), UniqueConstraint("company_id", "id", name="uq_ap_vendor_credits_company_id"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    credit_number: Mapped[str] = mapped_column(String(80), nullable=False)
    credit_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    available_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="issued")
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CreditApplication(Base):
    __tablename__ = "ap_credit_applications"
    __table_args__ = (ForeignKeyConstraint(["company_id", "credit_id"], ["ap_vendor_credits.company_id", "ap_vendor_credits.id"], ondelete="RESTRICT"), ForeignKeyConstraint(["company_id", "bill_id"], ["ap_bills.company_id", "ap_bills.id"], ondelete="RESTRICT"), CheckConstraint("amount > 0", name="ck_ap_credit_applications_amount"), UniqueConstraint("company_id", "idempotency_key", name="uq_ap_credit_application_idempotency"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    credit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    bill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class APSubledgerEntry(Base):
    __tablename__ = "ap_subledger_entries"
    __table_args__ = (CheckConstraint("entry_type IN ('bill','bill_reversal','credit','credit_application','credit_unapplication','disbursement','disbursement_reversal','correction')", name="ck_ap_subledger_entry_type"), UniqueConstraint("company_id", "idempotency_key", name="uq_ap_subledger_idempotency"), Index("ix_ap_subledger_as_of", "company_id", "vendor_id", "effective_date"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    posting_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Disbursement(Base):
    __tablename__ = "ap_disbursements"
    __table_args__ = (ForeignKeyConstraint(["company_id", "vendor_id"], ["ap_vendors.company_id", "ap_vendors.id"], ondelete="RESTRICT"), CheckConstraint("amount > 0 AND available_amount >= 0 AND available_amount <= amount", name="ck_ap_disbursements_amounts"), CheckConstraint("recorder_user_id <> approver_user_id", name="ck_ap_disbursements_sod"), UniqueConstraint("company_id", "source_system", "source_identity", name="uq_ap_disbursement_source"), UniqueConstraint("company_id", "id", name="uq_ap_disbursements_company_id"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    available_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    method_category: Mapped[str] = mapped_column(String(40), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorder_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    approver_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="recorded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DisbursementApplication(Base):
    __tablename__ = "ap_disbursement_applications"
    __table_args__ = (ForeignKeyConstraint(["company_id", "disbursement_id"], ["ap_disbursements.company_id", "ap_disbursements.id"], ondelete="RESTRICT"), ForeignKeyConstraint(["company_id", "bill_id"], ["ap_bills.company_id", "ap_bills.id"], ondelete="RESTRICT"), CheckConstraint("amount > 0", name="ck_ap_disbursement_applications_amount"), UniqueConstraint("company_id", "idempotency_key", name="uq_ap_disbursement_application_idempotency"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    disbursement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    bill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class APPostingReceipt(Base):
    __tablename__ = "ap_accounting_posting_receipts"
    __table_args__ = (UniqueConstraint("company_id", "source_event_id", name="uq_ap_posting_receipt_event"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    journal_version: Mapped[int | None] = mapped_column(Integer)
    mapping_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
