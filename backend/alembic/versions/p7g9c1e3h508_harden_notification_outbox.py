"""harden notification outbox resilience

Revision ID: q8h0d2f4i619
Revises: p7g9c1e3h608
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "q8h0d2f4i619"
down_revision: str | Sequence[str] | None = "p7g9c1e3h608"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_notification_outbox_status", "notification_outbox", type_="check"
    )
    op.drop_constraint(
        "ck_notification_outbox_lifecycle", "notification_outbox", type_="check"
    )
    op.add_column("notification_outbox", sa.Column("intent_digest", sa.String(64)))
    op.add_column(
        "notification_outbox", sa.Column("company_id", postgresql.UUID(as_uuid=True))
    )
    op.add_column(
        "notification_outbox", sa.Column("branch_id", postgresql.UUID(as_uuid=True))
    )
    op.add_column("notification_outbox", sa.Column("channel", sa.String(40)))
    op.add_column(
        "notification_outbox", sa.Column("recipient_reference", sa.String(160))
    )
    op.add_column(
        "notification_outbox",
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("notification_outbox", sa.Column("source_action", sa.String(120)))
    op.add_column("notification_outbox", sa.Column("template_version", sa.String(150)))
    op.add_column(
        "notification_outbox", sa.Column("actor_user_id", postgresql.UUID(as_uuid=True))
    )
    op.add_column(
        "notification_outbox", sa.Column("claim_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "notification_outbox", sa.Column("submitted_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "notification_outbox", sa.Column("ambiguous_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "notification_outbox",
        sa.Column(
            "provider_supports_idempotency",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "notification_outbox", sa.Column("provider_idempotency_key", sa.String(200))
    )
    op.add_column(
        "notification_outbox", sa.Column("provider_reference", sa.String(200))
    )
    op.add_column(
        "notification_outbox", sa.Column("archived_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_notification_outbox_company_id", "notification_outbox", ["company_id"]
    )
    op.create_index(
        "ix_notification_outbox_branch_id", "notification_outbox", ["branch_id"]
    )
    op.create_check_constraint(
        "ck_notification_outbox_status",
        "notification_outbox",
        "status IN ('pending','claimed','retry_scheduled','sent','failed','ambiguous','canceled','suppressed')",
    )
    op.create_check_constraint(
        "ck_notification_outbox_lifecycle",
        "notification_outbox",
        "(status = 'pending' AND claimed_at IS NULL AND claimed_by IS NULL AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'claimed' AND claimed_at IS NOT NULL AND claimed_by IS NOT NULL AND claim_token IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'retry_scheduled' AND claimed_at IS NULL AND claimed_by IS NULL AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL AND retry_count > 0) OR "
        "(status = 'sent' AND claim_token IS NULL AND sent_at IS NOT NULL AND failed_at IS NULL) OR "
        "(status = 'failed' AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NOT NULL AND terminal_failure = true) OR "
        "(status = 'ambiguous' AND claim_token IS NULL AND ambiguous_at IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status IN ('canceled','suppressed') AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL)",
    )
    op.create_table(
        "notification_delivery_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "outbox_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("worker_id", sa.String(120)),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True)),
        sa.Column("provider_reference", sa.String(200)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_category", sa.String(80)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason_digest", sa.String(64)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('claimed','submitted','delivered','retryable','failed','ambiguous','recovered','canceled','suppressed')",
            name="ck_notification_delivery_evidence_outcome",
        ),
        sa.UniqueConstraint(
            "outbox_id", "sequence", name="uq_notification_delivery_evidence_sequence"
        ),
    )
    op.create_index(
        "ix_notification_delivery_evidence_outbox",
        "notification_delivery_evidence",
        ["outbox_id", "sequence"],
    )
    op.execute("""
        CREATE FUNCTION reject_notification_delivery_evidence_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Notification delivery evidence is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_notification_delivery_evidence_immutable BEFORE UPDATE OR DELETE ON notification_delivery_evidence FOR EACH ROW EXECUTE FUNCTION reject_notification_delivery_evidence_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_notification_delivery_evidence_immutable ON notification_delivery_evidence"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS reject_notification_delivery_evidence_mutation()"
    )
    op.drop_index(
        "ix_notification_delivery_evidence_outbox",
        table_name="notification_delivery_evidence",
    )
    op.drop_table("notification_delivery_evidence")
    op.drop_constraint(
        "ck_notification_outbox_lifecycle", "notification_outbox", type_="check"
    )
    op.drop_constraint(
        "ck_notification_outbox_status", "notification_outbox", type_="check"
    )
    op.drop_index("ix_notification_outbox_branch_id", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_company_id", table_name="notification_outbox")
    for column in (
        "archived_at",
        "provider_reference",
        "provider_idempotency_key",
        "provider_supports_idempotency",
        "ambiguous_at",
        "submitted_at",
        "claim_expires_at",
        "actor_user_id",
        "template_version",
        "source_action",
        "source_event_id",
        "recipient_reference",
        "channel",
        "branch_id",
        "company_id",
        "intent_digest",
    ):
        op.drop_column("notification_outbox", column)
    op.create_check_constraint(
        "ck_notification_outbox_status",
        "notification_outbox",
        "status IN ('pending','claimed','retry_scheduled','sent','failed')",
    )
    op.create_check_constraint(
        "ck_notification_outbox_lifecycle",
        "notification_outbox",
        "(status = 'pending' AND claimed_at IS NULL AND claimed_by IS NULL AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'claimed' AND claimed_at IS NOT NULL AND claimed_by IS NOT NULL AND claim_token IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'retry_scheduled' AND claimed_at IS NULL AND claimed_by IS NULL AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL AND retry_count > 0) OR "
        "(status = 'sent' AND claim_token IS NULL AND sent_at IS NOT NULL AND failed_at IS NULL) OR "
        "(status = 'failed' AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NOT NULL AND terminal_failure = true)",
    )
