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


class NotificationOutbox(Base):
    """Durable delivery intent; provider delivery occurs after commit."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_notification_outbox_branch_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "branch_id IS NULL OR company_id IS NOT NULL",
            name="ck_notification_outbox_branch_requires_company",
        ),
        CheckConstraint(
            "length(btrim(notification_type)) > 0",
            name="ck_notification_outbox_type_not_blank",
        ),
        CheckConstraint(
            "length(btrim(template_identifier)) > 0",
            name="ck_notification_outbox_template_not_blank",
        ),
        CheckConstraint(
            "length(btrim(recipient)) > 0",
            name="ck_notification_outbox_recipient_not_blank",
        ),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="ck_notification_outbox_idempotency_key_not_blank",
        ),
        CheckConstraint(
            "status IN ('pending', 'claimed', 'retry_scheduled', 'sent', 'failed', 'ambiguous', 'canceled', 'suppressed')",
            name="ck_notification_outbox_status",
        ),
        CheckConstraint(
            "retry_count >= 0",
            name="ck_notification_outbox_retry_count",
        ),
        CheckConstraint(
            "(status = 'pending' AND claimed_at IS NULL AND claimed_by IS NULL "
            "AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'claimed' AND claimed_at IS NOT NULL "
            "AND claimed_by IS NOT NULL AND claim_token IS NOT NULL "
            "AND sent_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'retry_scheduled' AND claimed_at IS NULL "
            "AND claimed_by IS NULL AND claim_token IS NULL "
            "AND sent_at IS NULL AND failed_at IS NULL AND retry_count > 0) OR "
            "(status = 'sent' AND claim_token IS NULL AND sent_at IS NOT NULL "
            "AND failed_at IS NULL) OR "
            "(status = 'failed' AND claim_token IS NULL AND sent_at IS NULL "
            "AND failed_at IS NOT NULL AND terminal_failure = true) OR "
            "(status = 'ambiguous' AND claim_token IS NULL AND ambiguous_at IS NOT NULL "
            "AND sent_at IS NULL AND failed_at IS NULL) OR "
            "(status IN ('canceled', 'suppressed') AND claim_token IS NULL "
            "AND sent_at IS NULL AND failed_at IS NULL)",
            name="ck_notification_outbox_lifecycle",
        ),
        CheckConstraint(
            "terminal_failure = false OR status = 'failed'",
            name="ck_notification_outbox_terminal_failure",
        ),
        CheckConstraint(
            "sent_at IS NULL OR sent_at >= created_at",
            name="ck_notification_outbox_sent_timestamp",
        ),
        CheckConstraint(
            "failed_at IS NULL OR failed_at >= created_at",
            name="ck_notification_outbox_failed_timestamp",
        ),
        Index(
            "ix_notification_outbox_ready",
            "status",
            "scheduled_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_notification_outbox_claim_recovery",
            "status",
            "claimed_at",
        ),
        Index(
            "ix_notification_outbox_correlation_id",
            "correlation_id",
        ),
        Index(
            "ix_notification_outbox_terminal_cleanup",
            "status",
            "updated_at",
            postgresql_where=text("status IN ('sent', 'failed')"),
        ),
        Index(
            "uq_notification_outbox_claim_token",
            "claim_token",
            unique=True,
            postgresql_where=text("claim_token IS NOT NULL"),
        ),
        Index(
            "uq_notification_outbox_company_idempotency_key",
            "company_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("company_id IS NOT NULL"),
        ),
        Index(
            "uq_notification_outbox_unscoped_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("company_id IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False)
    template_identifier: Mapped[str] = mapped_column(String(150), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid4
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    intent_digest: Mapped[str | None] = mapped_column(String(64))
    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        index=True,
    )
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    channel: Mapped[str | None] = mapped_column(String(40))
    recipient_reference: Mapped[str | None] = mapped_column(String(160))
    source_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_events.id", ondelete="RESTRICT"),
    )
    source_action: Mapped[str | None] = mapped_column(String(120))
    template_version: Mapped[str | None] = mapped_column(String(150))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    terminal_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ambiguous_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_supports_idempotency: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    provider_idempotency_key: Mapped[str | None] = mapped_column(String(200))
    provider_reference: Mapped[str | None] = mapped_column(String(200))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_category: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDeliveryEvidence(Base):
    __tablename__ = "notification_delivery_evidence"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('claimed','submitted','delivered','retryable','failed','ambiguous','recovered','canceled','suppressed')",
            name="ck_notification_delivery_evidence_outcome",
        ),
        UniqueConstraint(
            "outbox_id", "sequence", name="uq_notification_delivery_evidence_sequence"
        ),
        Index("ix_notification_delivery_evidence_outbox", "outbox_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    outbox_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    worker_id: Mapped[str | None] = mapped_column(String(120))
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_reference: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_category: Mapped[str | None] = mapped_column(String(80))
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason_digest: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
