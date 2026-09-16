from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class FieldWorkNote(Base):
    __tablename__ = "field_work_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_notes_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "note_type IN ('work_performed','internal','customer_visible')",
            name="ck_field_notes_type",
        ),
        CheckConstraint("length(btrim(content)) > 0", name="ck_field_notes_content"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_notes_idempotency"
        ),
        Index("ix_field_notes_job_created", "company_id", "job_id", "created_at"),
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
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    note_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldCustomerApproval(Base):
    __tablename__ = "field_customer_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_approvals_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "disposition IN ('approved','unavailable','refused')",
            name="ck_field_approvals_disposition",
        ),
        CheckConstraint(
            "(disposition = 'approved' AND customer_name IS NOT NULL) OR (disposition <> 'approved' AND reason IS NOT NULL)",
            name="ck_field_approvals_evidence",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_approvals_idempotency"
        ),
        Index("ix_field_approvals_job_created", "company_id", "job_id", "created_at"),
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
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    disposition: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldInvoiceHandoff(Base):
    __tablename__ = "field_invoice_handoffs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_handoffs_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pending','completed','reconciliation_required')",
            name="ck_field_handoffs_status",
        ),
        UniqueConstraint("company_id", "job_id", name="uq_field_handoffs_job"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_handoffs_idempotency"
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
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
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


class FieldCompletionRequirementSnapshot(Base):
    __tablename__ = "field_completion_requirement_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_requirement_snapshots_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_field_requirement_snapshot_version"),
        CheckConstraint(
            "requirements_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_requirement_snapshot_fingerprint",
        ),
        UniqueConstraint(
            "company_id",
            "job_id",
            "version",
            name="uq_field_requirement_snapshot_version",
        ),
        UniqueConstraint(
            "company_id", "job_id", name="uq_field_requirement_snapshot_job"
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
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requirements: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    requirements_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldCompletionEvidence(Base):
    __tablename__ = "field_completion_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_completion_evidence_job",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "snapshot_id",
            "requirement_code",
            name="uq_field_evidence_requirement",
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
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_completion_requirement_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requirement_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldNonBillableDisposition(Base):
    __tablename__ = "field_non_billable_dispositions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_non_billable_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(btrim(reason)) > 0", name="ck_field_non_billable_reason"
        ),
        UniqueConstraint("company_id", "job_id", name="uq_field_non_billable_job"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_non_billable_idempotency"
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
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    authorized_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldArtifactIntent(Base):
    __tablename__ = "field_artifact_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_artifact_intent_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "artifact_class IN ('photo','field_document','equipment_evidence')",
            name="ck_field_artifact_intent_class",
        ),
        CheckConstraint("expected_size > 0", name="ck_field_artifact_intent_size"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_artifact_intent_command"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_class: Mapped[str] = mapped_column(String(40), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_size: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    opaque_upload_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldArtifactEvidence(Base):
    __tablename__ = "field_artifact_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_artifact_evidence_job",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "intent_id", name="uq_field_artifact_intent"),
        UniqueConstraint(
            "company_id", "job_id", "content_digest", name="uq_field_artifact_digest"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    intent_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_artifact_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_class: Mapped[str] = mapped_column(String(40), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    opaque_storage_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldPurchase(Base):
    """Receipt-backed purchase evidence; downstream stock/Job effects stay explicit."""

    __tablename__ = "field_purchases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_purchase_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('receipt_attached','extraction_pending','review_required','ready_for_disposition','submitted')",
            name="ck_field_purchase_state",
        ),
        CheckConstraint("version >= 1", name="ck_field_purchase_version"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_purchase_command"
        ),
        UniqueConstraint(
            "company_id",
            "disposition_idempotency_key",
            name="uq_field_purchase_disposition_submission",
        ),
        UniqueConstraint(
            "company_id", "receipt_artifact_id", name="uq_field_purchase_receipt"
        ),
        Index(
            "ix_field_purchase_review", "company_id", "branch_id", "state", "created_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    receipt_artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_artifact_evidence.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_stock_locations.id", ondelete="RESTRICT"),
    )
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="receipt_attached"
    )
    receipt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    disposition_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    disposition_request_digest: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
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


class FieldPurchaseExtraction(Base):
    __tablename__ = "field_purchase_extractions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_field_purchase_extraction_version"),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_field_purchase_currency",
        ),
        UniqueConstraint(
            "company_id",
            "field_purchase_id",
            "version",
            name="uq_field_purchase_extraction_version",
        ),
        UniqueConstraint(
            "company_id",
            "extraction_digest",
            name="uq_field_purchase_extraction_digest",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    field_purchase_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_purchases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(160))
    extraction_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    vendor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchasing_operational_vendors.id", ondelete="RESTRICT"),
    )
    vendor_text: Mapped[str | None] = mapped_column(String(240))
    transaction_reference: Mapped[str | None] = mapped_column(String(160))
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str | None] = mapped_column(String(3))
    structured_evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldPurchaseLine(Base):
    __tablename__ = "field_purchase_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_field_purchase_line_quantity"),
        CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name="ck_field_purchase_line_unit_price",
        ),
        CheckConstraint(
            "match_state IN ('exact','unmatched','review_required','non_inventory')",
            name="ck_field_purchase_line_match",
        ),
        UniqueConstraint(
            "company_id",
            "field_purchase_id",
            "line_number",
            name="uq_field_purchase_line_number",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    field_purchase_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_purchases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    extraction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_purchase_extractions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    vendor_code: Mapped[str | None] = mapped_column(String(160))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    extended_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    inventory_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="RESTRICT")
    )
    match_state: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence_evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )


class FieldPurchaseDisposition(Base):
    __tablename__ = "field_purchase_dispositions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_field_purchase_disposition_quantity"),
        CheckConstraint(
            "disposition IN ('used_on_this_job','keep_on_truck','return_or_unused','non_inventory')",
            name="ck_field_purchase_disposition_type",
        ),
        CheckConstraint(
            "state IN ('pending_review','confirmed','composed')",
            name="ck_field_purchase_disposition_state",
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_field_purchase_disposition_command",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    field_purchase_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_purchases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_purchase_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    inventory_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_stock_locations.id", ondelete="RESTRICT"),
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FieldPurchaseVendorMapping(Base):
    __tablename__ = "field_purchase_vendor_mappings"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(vendor_code)) > 0", name="ck_field_purchase_mapping_code"
        ),
        UniqueConstraint(
            "company_id",
            "vendor_id",
            "vendor_code",
            "version",
            name="uq_field_purchase_mapping_version",
        ),
        Index(
            "ix_field_purchase_mapping_active",
            "company_id",
            "vendor_id",
            "vendor_code",
            "active",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchasing_operational_vendors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vendor_code: Mapped[str] = mapped_column(String(160), nullable=False)
    inventory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("field_purchase_vendor_mappings.id", ondelete="RESTRICT"),
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    certified_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
