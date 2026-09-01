"""Add truthful provider acceptance evidence.

Revision ID: j6k4m72c9p5q
Revises: i5h3g51b8z4x
"""

import sqlalchemy as sa
from alembic import op

revision = "j6k4m72c9p5q"
down_revision = "i5h3g51b8z4x"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_delivery_evidence",
        sa.Column("provider_event_key", sa.String(200), nullable=True),
    )
    op.create_unique_constraint(
        "uq_notification_delivery_evidence_provider_event",
        "notification_delivery_evidence",
        ["outbox_id", "provider_event_key"],
    )
    op.drop_constraint("ck_notification_outbox_lifecycle", "notification_outbox", type_="check")
    op.drop_constraint("ck_notification_outbox_status", "notification_outbox", type_="check")
    op.create_check_constraint(
        "ck_notification_outbox_status",
        "notification_outbox",
        "status IN ('pending','claimed','retry_scheduled','accepted','sent','failed','ambiguous','canceled','suppressed')",
    )
    op.create_check_constraint(
        "ck_notification_outbox_lifecycle",
        "notification_outbox",
        "(status = 'pending' AND claimed_at IS NULL AND claimed_by IS NULL AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'claimed' AND claimed_at IS NOT NULL AND claimed_by IS NOT NULL AND claim_token IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'retry_scheduled' AND claimed_at IS NULL AND claimed_by IS NULL AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL AND retry_count > 0) OR "
        "(status = 'accepted' AND claim_token IS NULL AND submitted_at IS NOT NULL AND provider_reference IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'sent' AND claim_token IS NULL AND sent_at IS NOT NULL AND failed_at IS NULL) OR "
        "(status = 'failed' AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NOT NULL AND terminal_failure = true) OR "
        "(status = 'ambiguous' AND claim_token IS NULL AND ambiguous_at IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL) OR "
        "(status IN ('canceled','suppressed') AND claim_token IS NULL AND sent_at IS NULL AND failed_at IS NULL)",
    )
    op.drop_constraint("ck_notification_delivery_evidence_outcome", "notification_delivery_evidence", type_="check")
    op.create_check_constraint(
        "ck_notification_delivery_evidence_outcome",
        "notification_delivery_evidence",
        "outcome IN ('claimed','submitted','accepted','delivered','retryable','failed','ambiguous','recovered','canceled','suppressed','deferred','bounced','rejected','complaint','expired')",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM notification_outbox WHERE status = 'accepted') OR EXISTS (SELECT 1 FROM notification_delivery_evidence WHERE outcome IN ('accepted','deferred','bounced','rejected','complaint','expired')) THEN RAISE EXCEPTION 'cannot downgrade notification acceptance evidence'; END IF; END $$"
    )
    op.drop_constraint("ck_notification_delivery_evidence_outcome", "notification_delivery_evidence", type_="check")
    op.create_check_constraint(
        "ck_notification_delivery_evidence_outcome",
        "notification_delivery_evidence",
        "outcome IN ('claimed','submitted','delivered','retryable','failed','ambiguous','recovered','canceled','suppressed')",
    )
    op.drop_constraint("ck_notification_outbox_lifecycle", "notification_outbox", type_="check")
    op.drop_constraint("ck_notification_outbox_status", "notification_outbox", type_="check")
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
    op.drop_constraint(
        "uq_notification_delivery_evidence_provider_event",
        "notification_delivery_evidence",
        type_="unique",
    )
    op.drop_column("notification_delivery_evidence", "provider_event_key")
