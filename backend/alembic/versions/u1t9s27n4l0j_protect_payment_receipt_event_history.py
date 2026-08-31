"""Protect append-only payment receipt event history.

Revision ID: u1t9s27n4l0j
Revises: t0s8r16m3k9i
"""

from collections.abc import Sequence

from alembic import op

revision: str = "u1t9s27n4l0j"
down_revision: str | Sequence[str] | None = "t0s8r16m3k9i"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_payment_receipt_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Payment receipt event history is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_payment_receipt_events_immutable
        BEFORE UPDATE OR DELETE ON payment_receipt_events
        FOR EACH ROW EXECUTE FUNCTION reject_payment_receipt_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_payment_receipt_events_immutable "
        "ON payment_receipt_events"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_payment_receipt_event_mutation()")
