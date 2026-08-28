"""Persistence for immutable Workday Time evidence."""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PayPeriod(Base):
    __tablename__ = "timekeeping_pay_periods"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_time_pay_period_dates"),
        CheckConstraint(
            "processing_date >= period_end AND payday >= processing_date",
            name="ck_time_pay_period_processing",
        ),
        UniqueConstraint(
            "company_id", "period_start", "period_end", name="uq_time_pay_period"
        ),
        UniqueConstraint("company_id", "id", name="uq_time_pay_period_company"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    processing_date: Mapped[date] = mapped_column(Date, nullable=False)
    payday: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    schedule_definition_id: Mapped[str] = mapped_column(String(160), nullable=False)
    schedule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WorkdayPunchEvent(Base):
    __tablename__ = "timekeeping_punch_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "kind IN ('clock_in','clock_out','break_start','break_end')",
            name="ck_time_punch_kind",
        ),
        UniqueConstraint("company_id", "id", name="uq_time_punch_company"),
        UniqueConstraint(
            "company_id",
            "recorded_by_user_id",
            "idempotency_key",
            name="uq_time_punch_idempotency",
        ),
        Index(
            "ix_time_punch_employee_occurred",
            "company_id",
            "employee_id",
            "occurred_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_device_reference: Mapped[str | None] = mapped_column(String(200))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    event_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WorkdayTimeEntryRevision(Base):
    __tablename__ = "timekeeping_entry_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "provenance IN ('employee_punch','authorized_manual_entry')",
            name="ck_time_entry_provenance",
        ),
        CheckConstraint(
            "state IN ('recorded','submitted','approved','corrected')",
            name="ck_time_entry_state",
        ),
        CheckConstraint("revision_number >= 1", name="ck_time_entry_revision"),
        CheckConstraint(
            "(start_at IS NOT NULL AND end_at IS NOT NULL AND end_at > start_at) "
            "OR approved_duration_minutes IS NOT NULL",
            name="ck_time_entry_duration_shape",
        ),
        CheckConstraint(
            "approved_duration_minutes IS NULL OR approved_duration_minutes >= 0",
            name="ck_time_entry_duration",
        ),
        CheckConstraint(
            "(provenance = 'employee_punch' AND manual_reason IS NULL) OR "
            "(provenance = 'authorized_manual_entry' AND manual_reason IS NOT NULL)",
            name="ck_time_entry_manual_reason",
        ),
        UniqueConstraint(
            "company_id", "entry_id", "revision_number", name="uq_time_entry_revision"
        ),
        UniqueConstraint("company_id", "id", name="uq_time_entry_revision_company"),
        Index(
            "ix_time_entry_employee_date",
            "company_id",
            "employee_id",
            "work_date",
        ),
        Index(
            "uq_time_manual_idempotency",
            "company_id",
            "responsible_user_id",
            "origin_idempotency_key",
            unique=True,
            postgresql_where=text(
                "revision_number = 1 AND origin_idempotency_key IS NOT NULL"
            ),
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    entry_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("timekeeping_entry_revisions.id", ondelete="RESTRICT"),
    )
    lineage_revision_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    punch_event_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    manual_reason: Mapped[str | None] = mapped_column(Text)
    origin_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    origin_request_digest: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    source_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    responsible_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approval_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correction_reason: Mapped[str | None] = mapped_column(Text)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PayrollTimeInputRecord(Base):
    __tablename__ = "timekeeping_payroll_input_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "pay_period_id"],
            ["timekeeping_pay_periods.company_id", "timekeeping_pay_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "snapshot_digest", name="uq_time_payroll_snapshot_digest"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    snapshot_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_version: Mapped[str] = mapped_column(String(80), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    pay_period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    approved_revision_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    total_approved_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
