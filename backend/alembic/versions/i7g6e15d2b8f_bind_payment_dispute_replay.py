"""Bind Payment dispute replay and provider provenance.

Revision ID: i7g6e15d2b8f
Revises: h6f5d04c1a7e
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "i7g6e15d2b8f"
down_revision: str | None = "h6f5d04c1a7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_receipt_events",
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "payment_receipt_events",
        sa.Column("request_digest", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE payment_receipt_events
        SET provider_reference = 'legacy-evidence-unavailable:' || id::text,
            request_digest =
                md5(
                    'legacy:' || id::text || ':' || receipt_id::text || ':' ||
                    amount::text || ':' || evidence_digest || ':' || idempotency_key
                ) ||
                md5(
                    'legacy-proof:' || id::text || ':' || receipt_id::text || ':' ||
                    amount::text || ':' || evidence_digest || ':' || idempotency_key
                )
        WHERE event_type = 'dispute_recorded'
          AND provider_reference IS NULL
          AND request_digest IS NULL
        """
    )
    op.create_check_constraint(
        "ck_payment_receipt_events_dispute_evidence",
        "payment_receipt_events",
        "event_type <> 'dispute_recorded' OR "
        "(provider_reference IS NOT NULL AND length(btrim(provider_reference)) > 0 "
        "AND request_digest IS NOT NULL AND length(request_digest) = 64)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_payment_receipt_events_dispute_evidence",
        "payment_receipt_events",
        type_="check",
    )
    op.drop_column("payment_receipt_events", "request_digest")
    op.drop_column("payment_receipt_events", "provider_reference")
