"""create notification outbox

Revision ID: f2c8a4e6b193
Revises: e0a5c7d9f284
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f2c8a4e6b193"
down_revision: str | None = "e0a5c7d9f284"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column("template_identifier", sa.String(length=150), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("terminal_failure", sa.Boolean(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_by", sa.String(length=120)),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=80)),
        sa.Column("last_error_category", sa.String(length=80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(notification_type)) > 0",
            name="ck_notification_outbox_type_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(template_identifier)) > 0",
            name="ck_notification_outbox_template_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(recipient)) > 0",
            name="ck_notification_outbox_recipient_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="ck_notification_outbox_idempotency_key_not_blank",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'retry_scheduled', 'sent', 'failed')",
            name="ck_notification_outbox_status",
        ),
        sa.CheckConstraint(
            "retry_count >= 0", name="ck_notification_outbox_retry_count"
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "terminal_failure = false OR status = 'failed'",
            name="ck_notification_outbox_terminal_failure",
        ),
        sa.CheckConstraint(
            "sent_at IS NULL OR sent_at >= created_at",
            name="ck_notification_outbox_sent_timestamp",
        ),
        sa.CheckConstraint(
            "failed_at IS NULL OR failed_at >= created_at",
            name="ck_notification_outbox_failed_timestamp",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_outbox"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_notification_outbox_idempotency_key"
        ),
    )
    op.create_index(
        "ix_notification_outbox_ready",
        "notification_outbox",
        ["status", "scheduled_at", "created_at", "id"],
    )
    op.create_index(
        "ix_notification_outbox_claim_recovery",
        "notification_outbox",
        ["status", "claimed_at"],
    )
    op.create_index(
        "ix_notification_outbox_correlation_id",
        "notification_outbox",
        ["correlation_id"],
    )
    op.create_index(
        "ix_notification_outbox_terminal_cleanup",
        "notification_outbox",
        ["status", "updated_at"],
        postgresql_where=sa.text("status IN ('sent', 'failed')"),
    )
    op.create_index(
        "uq_notification_outbox_claim_token",
        "notification_outbox",
        ["claim_token"],
        unique=True,
        postgresql_where=sa.text("claim_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_notification_outbox_claim_token", table_name="notification_outbox"
    )
    op.drop_index(
        "ix_notification_outbox_terminal_cleanup",
        table_name="notification_outbox",
    )
    op.drop_index(
        "ix_notification_outbox_correlation_id", table_name="notification_outbox"
    )
    op.drop_index(
        "ix_notification_outbox_claim_recovery", table_name="notification_outbox"
    )
    op.drop_index("ix_notification_outbox_ready", table_name="notification_outbox")
    op.drop_table("notification_outbox")
