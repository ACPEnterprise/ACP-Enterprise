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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerImportBatch(Base):
    """Immutable source identity plus resumable state for a file staging run.

    This is intentionally separate from the HCP operational admission tables. A
    batch is only a validated roster staging boundary; downstream admission may
    consume it after its own identity and authorization checks.
    """

    __tablename__ = "customer_import_batches"
    __table_args__ = (
        UniqueConstraint("batch_key", name="uq_customer_import_batch_key"),
        UniqueConstraint("id", "company_id", "branch_id", name="uq_customer_import_batch_scope"),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "source_provider",
            "source_namespace",
            "source_sha256",
            "mapping_sha256",
            name="uq_customer_import_batch_source",
        ),
        CheckConstraint(
            "file_format IN ('csv', 'xlsx')", name="ck_customer_import_batch_format"
        ),
        CheckConstraint(
            "status IN ('staged', 'paused', 'completed', 'failed')",
            name="ck_customer_import_batch_status",
        ),
        CheckConstraint(
            "row_count >= 0 AND ready_count >= 0 AND duplicate_count >= 0 "
            "AND held_count >= 0 AND rejected_count >= 0 AND cursor_row >= 1",
            name="ck_customer_import_batch_counts",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_import_batch_branch_scope",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_customer_import_batches_tenant_created",
            "company_id",
            "branch_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_key: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    held_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="staged")
    migration_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customer_migration_runs.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CustomerImportRow(Base):
    """One immutable source row; no customer is created by this table."""

    __tablename__ = "customer_import_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_customer_import_row_number"),
        UniqueConstraint("batch_id", "source_identity_key", name="uq_customer_import_row_identity"),
        CheckConstraint(
            "disposition IN ('ready', 'duplicate', 'held', 'rejected')",
            name="ck_customer_import_row_disposition",
        ),
        Index("ix_customer_import_rows_batch_disposition", "batch_id", "disposition"),
        ForeignKeyConstraint(
            ["batch_id", "company_id", "branch_id"],
            [
                "customer_import_batches.id",
                "customer_import_batches.company_id",
                "customer_import_batches.branch_id",
            ],
            name="fk_customer_import_row_batch_scope",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_identity_key: Mapped[str] = mapped_column(String(400), nullable=False)
    source_row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    payload: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    validation_errors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerImportAuditEvent(Base):
    """Append-only, tenant-scoped audit evidence for staging and resume actions."""

    __tablename__ = "customer_import_audit_events"
    __table_args__ = (
        UniqueConstraint("batch_id", "event_key", name="uq_customer_import_audit_event"),
        ForeignKeyConstraint(
            ["batch_id", "company_id", "branch_id"],
            [
                "customer_import_batches.id",
                "customer_import_batches.company_id",
                "customer_import_batches.branch_id",
            ],
            name="fk_customer_import_audit_batch_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_customer_import_audit_tenant_created", "company_id", "branch_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_key: Mapped[str] = mapped_column(String(191), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
