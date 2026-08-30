from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


ACTIVE_ASSIGNMENT = (
    "status IN ('proposed','assigned','acknowledged','reconciliation_required')"
)


class DispatchAssignment(Base):
    __tablename__ = "dispatch_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_dispatch_assignments_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_dispatch_assignments_appointment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "primary_employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_dispatch_assignments_primary_employee",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_dispatch_assignments_job",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('proposed','assigned','acknowledged','released','replaced','cancelled','reconciliation_required')",
            name="ck_dispatch_assignments_status",
        ),
        CheckConstraint("version >= 1", name="ck_dispatch_assignments_version"),
        CheckConstraint(
            "window_end_at > window_start_at", name="ck_dispatch_assignments_window"
        ),
        CheckConstraint(
            "length(btrim(assignment_reason)) > 0",
            name="ck_dispatch_assignments_reason",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "appointment_id",
            name="uq_dispatch_assignments_appointment",
        ),
        UniqueConstraint("company_id", "id", name="uq_dispatch_assignments_company_id"),
        Index(
            "ix_dispatch_assignments_board",
            "company_id",
            "branch_id",
            "window_start_at",
            "status",
        ),
        Index(
            "ix_dispatch_assignments_primary_window",
            "company_id",
            "primary_employee_id",
            "window_start_at",
            "window_end_at",
            postgresql_where=text(
                "status IN ('proposed','assigned','acknowledged','reconciliation_required')"
            ),
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
    appointment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    primary_employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    assignment_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    assigned_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    window_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class DispatchCrewMember(Base):
    __tablename__ = "dispatch_crew_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["dispatch_assignments.company_id", "dispatch_assignments.id"],
            name="fk_dispatch_crew_assignment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_dispatch_crew_employee",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active','removed')", name="ck_dispatch_crew_status"
        ),
        CheckConstraint("version >= 1", name="ck_dispatch_crew_version"),
        Index(
            "uq_dispatch_crew_active",
            "company_id",
            "assignment_id",
            "employee_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_dispatch_crew_employee_active",
            "company_id",
            "employee_id",
            postgresql_where=text("status = 'active'"),
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
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    added_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    removed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removal_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class DispatchAssignmentHistory(Base):
    __tablename__ = "dispatch_assignment_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["dispatch_assignments.company_id", "dispatch_assignments.id"],
            name="fk_dispatch_history_assignment",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_dispatch_history_version"),
        CheckConstraint(
            "request_digest IS NULL OR length(request_digest) = 64",
            name="ck_dispatch_history_request_digest",
        ),
        UniqueConstraint(
            "company_id",
            "assignment_id",
            "version",
            name="uq_dispatch_history_assignment_version",
        ),
        Index(
            "ix_dispatch_history_assignment",
            "company_id",
            "assignment_id",
            "occurred_at",
        ),
        Index(
            "uq_dispatch_history_idempotency",
            "company_id",
            "evidence_reference",
            unique=True,
            postgresql_where=text("evidence_reference IS NOT NULL"),
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
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    prior_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(240))
    request_digest: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
