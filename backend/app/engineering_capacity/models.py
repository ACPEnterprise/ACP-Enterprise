from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.engineering_execution import (
    models as engineering_execution_models,  # noqa: F401
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringCapacityPolicy(Base):
    __tablename__ = "engineering_capacity_policies"
    __table_args__ = (
        CheckConstraint(
            "maximum_concurrent_workstreams >= 1",
            name="ck_capacity_policy_system_limit",
        ),
        CheckConstraint(
            "maximum_per_worker >= 1", name="ck_capacity_policy_worker_limit"
        ),
        CheckConstraint(
            "reserved_capacity >= 0", name="ck_capacity_policy_reserved_nonnegative"
        ),
        CheckConstraint(
            "reserved_capacity <= maximum_concurrent_workstreams",
            name="ck_capacity_policy_reserved_within_limit",
        ),
        CheckConstraint("version >= 1", name="ck_capacity_policy_version"),
        UniqueConstraint("company_id", name="uq_capacity_policy_company"),
        UniqueConstraint("company_id", "id", name="uq_capacity_policy_company_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    maximum_concurrent_workstreams: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    maximum_per_worker: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reserved_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auto_allocate_released_capacity: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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


class EngineeringCapacityMachine(Base):
    """Owner inventory. A label never implies enrollment or trust."""

    __tablename__ = "engineering_capacity_machines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(btrim(machine_label)) > 0", name="ck_capacity_machine_label"
        ),
        CheckConstraint(
            "enrollment_state IN ('unenrolled','enrolled','retired')",
            name="ck_capacity_machine_enrollment",
        ),
        CheckConstraint(
            "(enrollment_state = 'enrolled' AND worker_id IS NOT NULL) OR enrollment_state <> 'enrolled'",
            name="ck_capacity_machine_enrolled_worker",
        ),
        CheckConstraint("version >= 1", name="ck_capacity_machine_version"),
        UniqueConstraint(
            "company_id", "machine_label", name="uq_capacity_machine_label"
        ),
        UniqueConstraint("company_id", "worker_id", name="uq_capacity_machine_worker"),
        UniqueConstraint("company_id", "id", name="uq_capacity_machine_company_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    machine_label: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_available_on: Mapped[date | None] = mapped_column(Date)
    enrollment_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unenrolled"
    )
    worker_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringWorkerCapacity(Base):
    __tablename__ = "engineering_worker_capacities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "machine_id"],
            [
                "engineering_capacity_machines.company_id",
                "engineering_capacity_machines.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("configured_limit >= 1", name="ck_worker_capacity_limit"),
        CheckConstraint("allocated_capacity >= 0", name="ck_worker_capacity_allocated"),
        CheckConstraint("reserved_capacity >= 0", name="ck_worker_capacity_reserved"),
        CheckConstraint(
            "allocated_capacity + reserved_capacity <= configured_limit",
            name="ck_worker_capacity_within_limit",
        ),
        CheckConstraint(
            "operational_state IN ('available','occupied','reserved','paused','offline','unhealthy','reconciliation_required')",
            name="ck_worker_capacity_operational_state",
        ),
        CheckConstraint(
            "health_state IN ('healthy','degraded','unhealthy','unknown')",
            name="ck_worker_capacity_health_state",
        ),
        CheckConstraint("version >= 1", name="ck_worker_capacity_version"),
        UniqueConstraint("company_id", "worker_id", name="uq_worker_capacity_worker"),
        UniqueConstraint("company_id", "machine_id", name="uq_worker_capacity_machine"),
        UniqueConstraint("company_id", "id", name="uq_worker_capacity_company_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    machine_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    configured_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    allocated_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    operational_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="offline"
    )
    health_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringCapacityReservation(Base):
    __tablename__ = "engineering_capacity_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_capacity_id"],
            [
                "engineering_worker_capacities.company_id",
                "engineering_worker_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "command_id"],
            ["engineering_commands.company_id", "engineering_commands.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active','allocated','released','expired','reconciliation_required')",
            name="ck_capacity_reservation_status",
        ),
        CheckConstraint(
            "transition_source IN ('owner','automatic','system')",
            name="ck_capacity_reservation_source",
        ),
        CheckConstraint("version >= 1", name="ck_capacity_reservation_version"),
        CheckConstraint(
            "released_at IS NULL OR released_at >= reserved_at",
            name="ck_capacity_reservation_release_time",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_capacity_reservation_idempotency"
        ),
        UniqueConstraint("company_id", "id", name="uq_capacity_reservation_company_id"),
        Index(
            "uq_capacity_reservation_active_command",
            "company_id",
            "command_id",
            unique=True,
            postgresql_where=text(
                "status IN ('active','allocated','reconciliation_required')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_capacity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    owner_intent_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    transition_source: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringCapacityAllocation(Base):
    __tablename__ = "engineering_capacity_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_capacity_id"],
            [
                "engineering_worker_capacities.company_id",
                "engineering_worker_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reservation_id"],
            [
                "engineering_capacity_reservations.company_id",
                "engineering_capacity_reservations.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "command_id"],
            ["engineering_commands.company_id", "engineering_commands.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active','released','reconciliation_required')",
            name="ck_capacity_allocation_status",
        ),
        CheckConstraint(
            "transition_source IN ('owner','automatic','system')",
            name="ck_capacity_allocation_source",
        ),
        CheckConstraint("version >= 1", name="ck_capacity_allocation_version"),
        CheckConstraint(
            "released_at IS NULL OR released_at >= allocated_at",
            name="ck_capacity_allocation_release_time",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_capacity_allocation_idempotency"
        ),
        UniqueConstraint("company_id", "id", name="uq_capacity_allocation_company_id"),
        Index(
            "uq_capacity_allocation_active_command",
            "company_id",
            "command_id",
            unique=True,
            postgresql_where=text("status IN ('active','reconciliation_required')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_capacity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    reservation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    transition_source: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringCapacityEvent(Base):
    __tablename__ = "engineering_capacity_events"
    __table_args__ = (
        CheckConstraint("length(btrim(event_type)) > 0", name="ck_capacity_event_type"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_capacity_event_idempotency"
        ),
        Index("ix_capacity_events_company_occurred", "company_id", "occurred_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_capacity_policies.id", ondelete="RESTRICT"),
    )
    worker_capacity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_worker_capacities.id", ondelete="RESTRICT"),
    )
    reservation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_capacity_reservations.id", ondelete="RESTRICT"),
    )
    allocation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_capacity_allocations.id", ondelete="RESTRICT"),
    )
    transition_source: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
