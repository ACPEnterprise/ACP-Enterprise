# ruff: noqa: UP045 -- Optional keeps SQLAlchemy 2 annotation resolution Python 3.9-safe.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class FactoryControlEvent(Base):
    __tablename__ = "factory_control_events"
    __table_args__ = (
        CheckConstraint("length(btrim(event_type)) > 0", name="ck_factory_event_type"),
        CheckConstraint("length(btrim(lane_code)) > 0", name="ck_factory_event_lane"),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0", name="ck_factory_event_idempotency"
        ),
        UniqueConstraint("company_id", "id", name="uq_factory_events_company_id"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_factory_events_idempotency"
        ),
        Index("ix_factory_events_company_time", "company_id", "occurred_at", "id"),
        Index(
            "ix_factory_events_lane_time",
            "company_id",
            "lane_code",
            "occurred_at",
            "id",
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
    lane_code: Mapped[str] = mapped_column(String(80), nullable=False)
    milestone_code: Mapped[Optional[str]] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    lifecycle_state: Mapped[Optional[str]] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FactoryLaneState(Base):
    __tablename__ = "factory_lane_states"
    __table_args__ = (
        UniqueConstraint("company_id", "lane_code", name="uq_factory_lane_state_lane"),
        UniqueConstraint("company_id", "id", name="uq_factory_lane_states_company_id"),
        CheckConstraint("version >= 1", name="ck_factory_lane_state_version"),
        Index(
            "ix_factory_lane_state_company_status",
            "company_id",
            "lifecycle_state",
            "lane_code",
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
    lane_code: Mapped[str] = mapped_column(String(80), nullable=False)
    milestone_code: Mapped[Optional[str]] = mapped_column(String(160))
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False)
    queue_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_handoff_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FactoryControlSnapshot(Base):
    __tablename__ = "factory_control_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_factory_snapshots_company_id"),
        UniqueConstraint("company_id", "snapshot_key", name="uq_factory_snapshots_key"),
        Index("ix_factory_snapshots_company_time", "company_id", "captured_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_key: Mapped[str] = mapped_column(String(200), nullable=False)
    roadmap_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    lane_states: Mapped[list] = mapped_column(JSONB, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
