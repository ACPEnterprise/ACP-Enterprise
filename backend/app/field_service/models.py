from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id", "assignment_id"],
            [
                "dispatch_assignments.company_id",
                "dispatch_assignments.branch_id",
                "dispatch_assignments.job_id",
                "dispatch_assignments.id",
            ],
            name="fk_field_notes_assignment_scope",
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
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id", "assignment_id"],
            [
                "dispatch_assignments.company_id",
                "dispatch_assignments.branch_id",
                "dispatch_assignments.job_id",
                "dispatch_assignments.id",
            ],
            name="fk_field_approvals_assignment_scope",
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
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id", "assignment_id"],
            [
                "dispatch_assignments.company_id",
                "dispatch_assignments.branch_id",
                "dispatch_assignments.job_id",
                "dispatch_assignments.id",
            ],
            name="fk_field_handoffs_assignment_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id", "invoice_id"],
            [
                "invoices.company_id",
                "invoices.branch_id",
                "invoices.job_id",
                "invoices.id",
            ],
            name="fk_field_handoffs_invoice_scope",
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
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
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
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id", "assignment_id"],
            [
                "dispatch_assignments.company_id",
                "dispatch_assignments.branch_id",
                "dispatch_assignments.job_id",
                "dispatch_assignments.id",
            ],
            name="fk_field_requirement_snapshots_assignment_scope",
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
        UniqueConstraint(
            "company_id",
            "branch_id",
            "job_id",
            "id",
            name="uq_field_requirement_snapshots_evidence_scope",
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
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id", "snapshot_id"],
            [
                "field_completion_requirement_snapshots.company_id",
                "field_completion_requirement_snapshots.branch_id",
                "field_completion_requirement_snapshots.job_id",
                "field_completion_requirement_snapshots.id",
            ],
            name="fk_field_completion_evidence_snapshot_scope",
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
    snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id", "assignment_id"],
            [
                "dispatch_assignments.company_id",
                "dispatch_assignments.branch_id",
                "dispatch_assignments.job_id",
                "dispatch_assignments.id",
            ],
            name="fk_field_non_billable_assignment_scope",
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
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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
