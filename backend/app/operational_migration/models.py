from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class OperationalMigrationRun(Base):
    __tablename__ = "operational_migration_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('dry_run', 'import')",
            name="ck_operational_migration_runs_mode",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_operational_migration_runs_status",
        ),
        CheckConstraint(
            "source_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count",
            name="ck_operational_migration_runs_reconcile",
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
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    initiated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalMigrationProgress(Base):
    __tablename__ = "operational_migration_progress"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('job', 'appointment')",
            name="ck_operational_migration_progress_entity",
        ),
        CheckConstraint(
            "processed_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count AND processed_count <= source_count",
            name="ck_operational_migration_progress_reconcile",
        ),
        UniqueConstraint(
            "run_id", "entity_type", name="uq_operational_migration_progress_entity"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class OperationalMigrationException(Base):
    __tablename__ = "operational_migration_exceptions"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('job', 'appointment')",
            name="ck_operational_migration_exceptions_entity",
        ),
        CheckConstraint(
            "disposition IN ('rejected', 'duplicate', 'unresolved')",
            name="ck_operational_migration_exceptions_disposition",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    record_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id_sha256: Mapped[str | None] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JobSourceIdentity(Base):
    __tablename__ = "operational_migration_job_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_job_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_job_source_identity_customer_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "service_location_source_identity_id",
                "company_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "service_location_source_identities.id",
                "service_location_source_identities.company_id",
                "service_location_source_identities.customer_id",
                "service_location_source_identities.service_location_id",
            ],
            name="fk_job_source_identity_location_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_job_id",
            name="uq_job_source_identity",
        ),
        UniqueConstraint(
            "company_id", "source_system", "job_id", name="uq_job_source_target"
        ),
        UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            "job_id",
            "customer_id",
            "service_location_id",
            name="uq_job_source_parent_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    customer_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    service_location_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_job_number: Mapped[str | None] = mapped_column(String(191))
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    assigned_technician_source_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AppointmentSourceIdentity(Base):
    __tablename__ = "operational_migration_appointment_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_appointment_source_identity_appointment_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "job_source_identity_id",
                "company_id",
                "branch_id",
                "job_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "operational_migration_job_source_identities.id",
                "operational_migration_job_source_identities.company_id",
                "operational_migration_job_source_identities.branch_id",
                "operational_migration_job_source_identities.job_id",
                "operational_migration_job_source_identities.customer_id",
                "operational_migration_job_source_identities.service_location_id",
            ],
            name="fk_appointment_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_appointment_id",
            name="uq_appointment_source_identity",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "appointment_id",
            name="uq_appointment_source_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_source_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_appointment_id: Mapped[str] = mapped_column(String(191), nullable=False)
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    assigned_technician_source_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    external_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    first_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operational_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
