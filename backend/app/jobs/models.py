from datetime import datetime, timezone
from typing import TYPE_CHECKING
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
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.scheduling.models import Appointment


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobNumberSequence(Base):
    __tablename__ = "job_number_sequences"
    __table_args__ = (
        CheckConstraint("last_value >= 0", name="ck_job_number_sequences_last_value"),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_job_number_sequences_company_id_companies",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_jobs_company_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint("job_number ~ '^JOB-[0-9]{6,}$'", name="ck_jobs_number_format"),
        CheckConstraint(
            "status IN ('draft', 'ready', 'in_progress', 'paused', "
            "'completed', 'cancelled')",
            name="ck_jobs_status",
        ),
        CheckConstraint(
            "job_type_code IS NULL OR job_type_code ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_jobs_type_code_format",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent', 'emergency')",
            name="ck_jobs_priority",
        ),
        CheckConstraint(
            "customer_reported_problem IS NULL OR "
            "length(btrim(customer_reported_problem)) > 0",
            name="ck_jobs_customer_problem_not_blank",
        ),
        CheckConstraint(
            "internal_description IS NULL OR length(btrim(internal_description)) > 0",
            name="ck_jobs_internal_description_not_blank",
        ),
        CheckConstraint("concurrency_version >= 1", name="ck_jobs_concurrency_version"),
        CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL) OR "
            "(status IN ('ready', 'in_progress', 'paused', 'completed') "
            "AND activated_at IS NOT NULL) OR status = 'cancelled'",
            name="ck_jobs_activation_state",
        ),
        CheckConstraint(
            "(status IN ('in_progress', 'paused', 'completed') "
            "AND started_at IS NOT NULL) OR "
            "(status IN ('draft', 'ready') AND started_at IS NULL) OR "
            "status = 'cancelled'",
            name="ck_jobs_start_state",
        ),
        CheckConstraint(
            "(status = 'paused' AND paused_at IS NOT NULL "
            "AND pause_reason_code IS NOT NULL) OR "
            "(status <> 'paused' AND paused_at IS NULL "
            "AND pause_reason_code IS NULL)",
            name="ck_jobs_pause_state",
        ),
        CheckConstraint(
            "pause_reason_code IS NULL OR length(btrim(pause_reason_code)) > 0",
            name="ck_jobs_pause_reason_not_blank",
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL)",
            name="ck_jobs_completion_state",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancelled_by_user_id IS NOT NULL "
            "AND cancellation_reason_code IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL "
            "AND cancelled_by_user_id IS NULL "
            "AND cancellation_reason_code IS NULL)",
            name="ck_jobs_cancellation_state",
        ),
        CheckConstraint(
            "cancellation_reason_code IS NULL OR "
            "length(btrim(cancellation_reason_code)) > 0",
            name="ck_jobs_cancellation_reason_not_blank",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_jobs_updated_at"),
        UniqueConstraint("company_id", "job_number", name="uq_jobs_company_number"),
        UniqueConstraint(
            "company_id", "branch_id", "id", name="uq_jobs_company_branch_id"
        ),
        Index(
            "ix_jobs_company_branch_status_created",
            "company_id",
            "branch_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_jobs_company_status_priority_created",
            "company_id",
            "status",
            "priority",
            "created_at",
            "id",
        ),
        Index(
            "ix_jobs_company_customer_created",
            "company_id",
            "customer_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_jobs_company_service_location_created",
            "company_id",
            "service_location_id",
            "created_at",
            "id",
        ),
        Index("ix_jobs_company_completed", "company_id", "completed_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_jobs_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_number: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "customers.id", name="fk_jobs_customer_id_customers", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "service_locations.id",
            name="fk_jobs_service_location_id_service_locations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    job_type_code: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    customer_reported_problem: Mapped[str | None] = mapped_column(Text)
    internal_description: Mapped[str | None] = mapped_column(Text)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pause_reason_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_jobs_completed_by_user_id_users", ondelete="RESTRICT"
        ),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_jobs_cancelled_by_user_id_users", ondelete="RESTRICT"
        ),
    )
    cancellation_reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_jobs_created_by_user_id_users", ondelete="RESTRICT"
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_jobs_updated_by_user_id_users", ondelete="RESTRICT"
        ),
    )

    appointment_links: Mapped[list["JobAppointmentLink"]] = relationship(
        back_populates="job", passive_deletes=True
    )


class JobAppointmentLink(Base):
    __tablename__ = "job_appointment_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_job_appointment_links_job",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_job_appointment_links_appointment",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "visit_sequence >= 1", name="ck_job_appointment_links_visit_sequence"
        ),
        UniqueConstraint(
            "job_id", "appointment_id", name="uq_job_appointment_links_job_appointment"
        ),
        UniqueConstraint(
            "job_id", "visit_sequence", name="uq_job_appointment_links_job_visit"
        ),
        Index(
            "ix_job_appointment_links_company_branch",
            "company_id",
            "branch_id",
            "job_id",
            "visit_sequence",
        ),
        Index("ix_job_appointment_links_appointment", "appointment_id", "job_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_job_appointment_links_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    visit_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    linked_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_job_appointment_links_linked_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )

    job: Mapped[Job] = relationship(back_populates="appointment_links")
    appointment: Mapped["Appointment"] = relationship(viewonly=True)
