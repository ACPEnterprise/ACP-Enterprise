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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringWorker(Base):
    __tablename__ = "engineering_workers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["registered_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_workers_registering_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(btrim(provider_identifier)) > 0",
            name="ck_engineering_workers_provider_not_blank",
        ),
        CheckConstraint(
            "length(btrim(name)) > 0", name="ck_engineering_workers_name_not_blank"
        ),
        CheckConstraint(
            "length(btrim(worker_version)) > 0",
            name="ck_engineering_workers_worker_version_not_blank",
        ),
        CheckConstraint(
            "lifecycle_state IN "
            "('registered','available','leased','offline','disabled')",
            name="ck_engineering_workers_lifecycle_state",
        ),
        CheckConstraint("version >= 1", name="ck_engineering_workers_version"),
        CheckConstraint(
            "updated_at >= registered_at",
            name="ck_engineering_workers_updated_at",
        ),
        UniqueConstraint(
            "company_id",
            "provider_identifier",
            "name",
            name="uq_engineering_workers_company_provider_name",
        ),
        UniqueConstraint("company_id", "id", name="uq_engineering_workers_company_id"),
        Index(
            "ix_engineering_workers_company_state",
            "company_id",
            "lifecycle_state",
            "registered_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_engineering_workers_company",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    provider_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    worker_version: Mapped[str] = mapped_column(String(50), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False)
    registered_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WorkerLease(Base):
    __tablename__ = "engineering_worker_leases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_leases_worker",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_worker_leases_execution",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active','expired','released')",
            name="ck_worker_leases_status",
        ),
        CheckConstraint("version >= 1", name="ck_worker_leases_version"),
        CheckConstraint("expires_at > started_at", name="ck_worker_leases_expiration"),
        CheckConstraint(
            "released_at IS NULL OR released_at >= started_at",
            name="ck_worker_leases_released_at",
        ),
        UniqueConstraint("company_id", "id", name="uq_worker_leases_company_id"),
        Index(
            "uq_worker_leases_active_execution",
            "company_id",
            "execution_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_worker_leases_active_worker",
            "company_id",
            "worker_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_worker_leases_company_status_expiration",
            "company_id",
            "status",
            "expires_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    capability_required: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WorkerHeartbeat(Base):
    __tablename__ = "engineering_worker_heartbeats"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_heartbeats_worker",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "health IN ('healthy','degraded','unhealthy')",
            name="ck_worker_heartbeats_health",
        ),
        CheckConstraint("worker_version >= 1", name="ck_worker_heartbeats_version"),
        UniqueConstraint(
            "company_id",
            "worker_id",
            "worker_version",
            name="uq_worker_heartbeats_worker_version",
        ),
        Index(
            "ix_worker_heartbeats_worker_seen",
            "company_id",
            "worker_id",
            "last_seen",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    health: Mapped[str] = mapped_column(String(20), nullable=False)
    worker_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WorkerResult(Base):
    __tablename__ = "engineering_worker_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_worker_results_worker",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "lease_id"],
            ["engineering_worker_leases.company_id", "engineering_worker_leases.id"],
            name="fk_worker_results_lease",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_worker_results_execution",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status = 'not_executed'", name="ck_worker_results_status"),
        CheckConstraint(
            "failure_classification = 'execution_not_connected'",
            name="ck_worker_results_failure",
        ),
        UniqueConstraint(
            "company_id", "lease_id", name="uq_worker_results_company_lease"
        ),
        Index(
            "ix_worker_results_company_execution",
            "company_id",
            "execution_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lease_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output_references: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    failure_classification: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
