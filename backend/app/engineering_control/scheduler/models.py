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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringSchedulerSnapshot(Base):
    __tablename__ = "engineering_scheduler_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "scheduler_version", name="uq_scheduler_snapshot_version"
        ),
        UniqueConstraint(
            "company_id", "fingerprint", name="uq_scheduler_snapshot_fingerprint"
        ),
        CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'", name="ck_scheduler_snapshot_fingerprint"
        ),
        CheckConstraint("version >= 1", name="ck_scheduler_snapshot_row_version"),
        Index(
            "uq_scheduler_snapshot_active_company",
            "company_id",
            unique=True,
            postgresql_where=text("active"),
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
    scheduler_version: Mapped[str] = mapped_column(String(80), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_documents: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EngineeringPermanentCapacity(Base):
    __tablename__ = "engineering_permanent_capacities"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "identity_code", name="uq_permanent_capacity_code"
        ),
        UniqueConstraint("company_id", "id", name="uq_permanent_capacity_company_id"),
        CheckConstraint(
            "identity_code IN ('OM1','OM2','MIG','ECO','LAP')",
            name="ck_permanent_capacity_code",
        ),
        CheckConstraint(
            "state IN ('available','unavailable','reconciliation_required')",
            name="ck_permanent_capacity_state",
        ),
        CheckConstraint("version >= 1", name="ck_permanent_capacity_version"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    identity_code: Mapped[str] = mapped_column(String(8), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unavailable"
    )
    reconciliation_reason: Mapped[str | None] = mapped_column(String(240))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringCapacityBinding(Base):
    __tablename__ = "engineering_capacity_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "permanent_capacity_id"],
            [
                "engineering_permanent_capacities.company_id",
                "engineering_permanent_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "worker_capacity_id"],
            [
                "engineering_worker_capacities.company_id",
                "engineering_worker_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('candidate','active','superseded','reconciliation_required')",
            name="ck_capacity_binding_state",
        ),
        CheckConstraint("version >= 1", name="ck_capacity_binding_version"),
        Index(
            "uq_capacity_binding_active_identity",
            "company_id",
            "permanent_capacity_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    permanent_capacity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    worker_capacity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    bound_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EngineeringSchedulerEvent(Base):
    __tablename__ = "engineering_scheduler_events"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_scheduler_event_idempotency"
        ),
        Index("ix_scheduler_event_company_time", "company_id", "occurred_at", "id"),
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
    scheduler_version: Mapped[str] = mapped_column(String(80), nullable=False)
    milestone_code: Mapped[str | None] = mapped_column(String(80))
    permanent_capacity_identity: Mapped[str | None] = mapped_column(String(8))
    record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
