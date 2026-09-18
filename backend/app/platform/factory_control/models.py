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


class PlatformAuthorityAssignment(Base):
    """Audited, explicit platform authority; never inferred from tenant roles."""

    __tablename__ = "platform_authority_assignments"
    __table_args__ = (
        CheckConstraint(
            "principal_type IN ('USER','WORKER_IDENTITY')",
            name="ck_platform_authority_principal_type",
        ),
        CheckConstraint(
            "authority_code IN ('PLATFORM_OWNER','PLATFORM_ADMIN','FACTORY_CONTROLLER')",
            name="ck_platform_authority_code",
        ),
        CheckConstraint(
            "permission_code IN ('PLATFORM_FACTORY_CONTROL_READ',"
            "'PLATFORM_FACTORY_CONTROL_INGEST',"
            "'PLATFORM_FACTORY_CONTROL_SNAPSHOT')",
            name="ck_platform_authority_permission",
        ),
        CheckConstraint(
            "(principal_type = 'USER' AND user_id IS NOT NULL "
            "AND worker_identity_id IS NULL "
            "AND authority_code IN ('PLATFORM_OWNER','PLATFORM_ADMIN') "
            "AND permission_code = 'PLATFORM_FACTORY_CONTROL_READ') OR "
            "(principal_type = 'WORKER_IDENTITY' AND user_id IS NULL "
            "AND worker_identity_id IS NOT NULL "
            "AND authority_code = 'FACTORY_CONTROLLER' "
            "AND permission_code IN ('PLATFORM_FACTORY_CONTROL_INGEST',"
            "'PLATFORM_FACTORY_CONTROL_SNAPSHOT'))",
            name="ck_platform_authority_principal_semantics",
        ),
        CheckConstraint(
            "status IN ('active','revoked')", name="ck_platform_authority_status"
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL "
            "AND revoked_by_user_id IS NULL AND revocation_reason IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL "
            "AND revoked_by_user_id IS NOT NULL "
            "AND length(btrim(revocation_reason)) > 0)",
            name="ck_platform_authority_revocation",
        ),
        CheckConstraint("version >= 1", name="ck_platform_authority_version"),
        CheckConstraint(
            "length(btrim(grant_reason)) > 0",
            name="ck_platform_authority_grant_reason",
        ),
        Index(
            "uq_platform_authority_active_user_permission",
            "user_id",
            "permission_code",
            unique=True,
            postgresql_where=text("status = 'active' AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_platform_authority_active_worker_permission",
            "worker_identity_id",
            "permission_code",
            unique=True,
            postgresql_where=text(
                "status = 'active' AND worker_identity_id IS NOT NULL"
            ),
        ),
        Index(
            "ix_platform_authority_user_status",
            "user_id",
            "status",
            "permission_code",
        ),
        Index(
            "ix_platform_authority_worker_status",
            "worker_identity_id",
            "status",
            "permission_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    principal_type: Mapped[str] = mapped_column(String(24), nullable=False)
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    worker_identity_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("worker_identities.id", ondelete="RESTRICT")
    )
    authority_code: Mapped[str] = mapped_column(String(40), nullable=False)
    permission_code: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    grant_reason: Mapped[str] = mapped_column(Text, nullable=False)
    granted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    revoked_by_user_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FactoryControlEvent(Base):
    __tablename__ = "factory_control_events"
    __table_args__ = (
        CheckConstraint("length(btrim(event_type)) > 0", name="ck_factory_event_type"),
        CheckConstraint("length(btrim(lane_code)) > 0", name="ck_factory_event_lane"),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0", name="ck_factory_event_idempotency"
        ),
        CheckConstraint(
            "length(request_digest) = 64", name="ck_factory_event_request_digest"
        ),
        CheckConstraint("queue_depth >= 0", name="ck_factory_event_queue_depth"),
        CheckConstraint(
            "controlling_enterprise IS NULL OR "
            "controlling_enterprise IN ('OM1E','OM2E','LaptopE')",
            name="ck_factory_event_controller",
        ),
        CheckConstraint(
            "self_refill_health IS NULL OR self_refill_health IN "
            "('SELF_REFILL_HEALTHY','ELIGIBLE_IDLE','WAITING_INTEGRATION',"
            "'HUMAN_GATE','PROVIDER_GATE','DEPENDENCY_BLOCKED','RATE_LIMITED',"
            "'UNSAFE_STOP','UNKNOWN')",
            name="ck_factory_event_self_refill",
        ),
        UniqueConstraint("idempotency_key", name="uq_factory_events_idempotency"),
        Index("ix_factory_events_time", "occurred_at", "id"),
        Index("ix_factory_events_lane_time", "lane_code", "occurred_at", "id"),
        Index(
            "ix_factory_events_tenant_time", "tenant_company_id", "occurred_at", "id"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_company_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT")
    )
    lane_code: Mapped[str] = mapped_column(String(80), nullable=False)
    milestone_code: Mapped[Optional[str]] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    lifecycle_state: Mapped[Optional[str]] = mapped_column(String(40))
    queue_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine: Mapped[Optional[str]] = mapped_column(String(120))
    current_assignment: Mapped[Optional[str]] = mapped_column(String(200))
    next_queued_item: Mapped[Optional[str]] = mapped_column(String(200))
    controlling_enterprise: Mapped[Optional[str]] = mapped_column(String(20))
    self_refill_health: Mapped[Optional[str]] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    controller_worker_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_identities.id", ondelete="RESTRICT"),
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
        UniqueConstraint("lane_code", name="uq_factory_lane_state_lane"),
        CheckConstraint("version >= 1", name="ck_factory_lane_state_version"),
        CheckConstraint("queue_depth >= 0", name="ck_factory_lane_queue_depth"),
        CheckConstraint(
            "controlling_enterprise IS NULL OR "
            "controlling_enterprise IN ('OM1E','OM2E','LaptopE')",
            name="ck_factory_lane_controller",
        ),
        CheckConstraint(
            "self_refill_health IS NULL OR self_refill_health IN "
            "('SELF_REFILL_HEALTHY','ELIGIBLE_IDLE','WAITING_INTEGRATION',"
            "'HUMAN_GATE','PROVIDER_GATE','DEPENDENCY_BLOCKED','RATE_LIMITED',"
            "'UNSAFE_STOP','UNKNOWN')",
            name="ck_factory_lane_self_refill",
        ),
        Index("ix_factory_lane_state_status", "lifecycle_state", "lane_code"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    lane_code: Mapped[str] = mapped_column(String(80), nullable=False)
    milestone_code: Mapped[Optional[str]] = mapped_column(String(160))
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False)
    queue_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    machine: Mapped[Optional[str]] = mapped_column(String(120))
    current_assignment: Mapped[Optional[str]] = mapped_column(String(200))
    next_queued_item: Mapped[Optional[str]] = mapped_column(String(200))
    controlling_enterprise: Mapped[Optional[str]] = mapped_column(String(20))
    self_refill_health: Mapped[Optional[str]] = mapped_column(String(40))
    active_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    eligible_idle_since: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    last_handoff_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("factory_control_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FactoryControlSnapshot(Base):
    __tablename__ = "factory_control_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_key", name="uq_factory_snapshots_key"),
        CheckConstraint(
            "length(request_digest) = 64", name="ck_factory_snapshot_request_digest"
        ),
        Index("ix_factory_snapshots_time", "captured_at", "id"),
        Index(
            "ix_factory_snapshots_tenant_time",
            "tenant_company_id",
            "captured_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_company_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT")
    )
    snapshot_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    roadmap_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    lane_states: Mapped[list] = mapped_column(JSONB, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by_worker_identity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
