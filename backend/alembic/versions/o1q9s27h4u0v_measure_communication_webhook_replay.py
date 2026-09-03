"""Measure authenticated communication webhook replay evidence.

Revision ID: o1q9s27h4u0v
Revises: n0p8r16g3t9u
"""

from alembic import op

revision = "o1q9s27h4u0v"
down_revision = "n0p8r16g3t9u"
branch_labels = None
depends_on = None


_PRIOR_OUTCOMES = (
    "'claimed','submitted','accepted','delivered','retryable','failed','ambiguous',"
    "'recovered','canceled','suppressed','deferred','bounced','rejected','complaint',"
    "'expired'"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_notification_delivery_evidence_outcome",
        "notification_delivery_evidence",
        type_="check",
    )
    op.create_check_constraint(
        "ck_notification_delivery_evidence_outcome",
        "notification_delivery_evidence",
        f"outcome IN ({_PRIOR_OUTCOMES},'webhook_replay')",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM notification_delivery_evidence "
        "WHERE outcome = 'webhook_replay') THEN RAISE EXCEPTION "
        "'cannot downgrade communication webhook replay evidence'; END IF; END $$"
    )
    op.drop_constraint(
        "ck_notification_delivery_evidence_outcome",
        "notification_delivery_evidence",
        type_="check",
    )
    op.create_check_constraint(
        "ck_notification_delivery_evidence_outcome",
        "notification_delivery_evidence",
        f"outcome IN ({_PRIOR_OUTCOMES})",
    )
