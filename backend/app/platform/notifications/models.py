from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationOutbox(Base):
    """Durable delivery intent; provider delivery occurs after commit."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
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
            "status IN ('pending', 'claimed', 'retry_scheduled', 'sent', 'failed')",
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
            "AND failed_at IS NOT NULL AND terminal_failure = true)",
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
    idempotency_key: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
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
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_category: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
