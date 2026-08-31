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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BusinessEvent(Base):
    __tablename__ = "business_events"
    __table_args__ = (
        CheckConstraint(
            "branch_id IS NULL OR company_id IS NOT NULL",
            name="ck_business_events_branch_requires_company",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_business_events_company_branch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_business_events_company_id"),
        UniqueConstraint("id", "branch_id", name="uq_business_events_id_branch"),
        Index(
            "ix_business_events_customer_timeline_entity",
            "company_id",
            "entity_type",
            "entity_id",
            "occurred_at",
            "id",
        ),
        Index(
            "ix_business_events_customer_timeline_payload",
            "company_id",
            text("(payload ->> 'customer_id')"),
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    branch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        default=uuid4,
        index=True,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class BusinessEventDelivery(Base):
    __tablename__ = "business_event_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','claimed','retryable','delivered','terminal')",
            name="ck_business_event_delivery_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_business_event_attempt_count"),
        CheckConstraint("replay_count >= 0", name="ck_business_event_replay_count"),
        CheckConstraint(
            "branch_id IS NULL OR company_id IS NOT NULL",
            name="ck_business_event_delivery_branch_requires_company",
        ),
        ForeignKeyConstraint(
            ["company_id", "event_id"],
            ["business_events.company_id", "business_events.id"],
            name="fk_business_event_delivery_company_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["event_id", "branch_id"],
            ["business_events.id", "business_events.branch_id"],
            name="fk_business_event_delivery_event_branch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_business_event_delivery_company_id"
        ),
        UniqueConstraint("id", "event_id", name="uq_business_event_delivery_id_event"),
        UniqueConstraint(
            "id", "branch_id", name="uq_business_event_delivery_id_branch"
        ),
        UniqueConstraint(
            "id", "consumer_name", name="uq_business_event_delivery_id_consumer"
        ),
        UniqueConstraint(
            "event_id", "consumer_name", name="uq_business_event_delivery_consumer"
        ),
        Index(
            "ix_business_event_delivery_ready",
            "status",
            "next_attempt_at",
            "created_at",
            "id",
        ),
        Index("ix_business_event_delivery_scope", "company_id", "branch_id"),
        Index(
            "uq_business_event_delivery_claim_token",
            "claim_token",
            unique=True,
            postgresql_where=text("claim_token IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    consumer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    event_version: Mapped[str] = mapped_column(String(40), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_category: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class BusinessEventDeliveryEvidence(Base):
    __tablename__ = "business_event_delivery_evidence"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('claimed','recovered','delivered','idempotent','retryable','terminal','replay_requested')",
            name="ck_business_event_delivery_evidence_outcome",
        ),
        CheckConstraint(
            "branch_id IS NULL OR company_id IS NOT NULL",
            name="ck_business_event_evidence_branch_requires_company",
        ),
        ForeignKeyConstraint(
            ["company_id", "delivery_id"],
            ["business_event_deliveries.company_id", "business_event_deliveries.id"],
            name="fk_business_event_evidence_company_delivery",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["delivery_id", "event_id"],
            ["business_event_deliveries.id", "business_event_deliveries.event_id"],
            name="fk_business_event_evidence_delivery_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["delivery_id", "branch_id"],
            ["business_event_deliveries.id", "business_event_deliveries.branch_id"],
            name="fk_business_event_evidence_delivery_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["delivery_id", "consumer_name"],
            ["business_event_deliveries.id", "business_event_deliveries.consumer_name"],
            name="fk_business_event_evidence_delivery_consumer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "delivery_id",
            "evidence_sequence",
            name="uq_business_event_evidence_sequence",
        ),
        Index(
            "uq_business_event_replay_request",
            "request_id",
            unique=True,
            postgresql_where=text("request_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    delivery_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_event_deliveries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    consumer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    evidence_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(120))
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_category: Mapped[str | None] = mapped_column(String(40))
    outcome_digest: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class BusinessEventConsumerReceipt(Base):
    __tablename__ = "business_event_consumer_receipts"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "consumer_name", name="uq_business_event_consumer_receipt"
        ),
        CheckConstraint(
            "branch_id IS NULL OR company_id IS NOT NULL",
            name="ck_business_event_receipt_branch_requires_company",
        ),
        ForeignKeyConstraint(
            ["company_id", "event_id"],
            ["business_events.company_id", "business_events.id"],
            name="fk_business_event_receipt_company_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["event_id", "branch_id"],
            ["business_events.id", "business_events.branch_id"],
            name="fk_business_event_receipt_event_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["event_id", "consumer_name"],
            [
                "business_event_deliveries.event_id",
                "business_event_deliveries.consumer_name",
            ],
            name="fk_business_event_receipt_registered_delivery",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    consumer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    outcome_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_sequence: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class BusinessEventConsumerCursor(Base):
    __tablename__ = "business_event_consumer_cursors"
    __table_args__ = (
        UniqueConstraint(
            "consumer_name",
            "company_id",
            "entity_type",
            "entity_id",
            name="uq_business_event_consumer_cursor",
        ),
        ForeignKeyConstraint(
            ["company_id", "last_event_id"],
            ["business_events.company_id", "business_events.id"],
            name="fk_business_event_cursor_company_event",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    consumer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
