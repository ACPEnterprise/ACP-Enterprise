"""harden Business Event delivery and replay

Revision ID: n5e7a9c1f386
Revises: m4d6z8b0e275
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "n5e7a9c1f386"
down_revision: str | Sequence[str] | None = "m4d6z8b0e275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_event_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("consumer_name", sa.String(160), nullable=False),
        sa.Column("event_version", sa.String(40), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("replay_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_by", sa.String(120)),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("last_error_category", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','claimed','retryable','delivered','terminal')",
            name="ck_business_event_delivery_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_business_event_attempt_count"
        ),
        sa.CheckConstraint("replay_count >= 0", name="ck_business_event_replay_count"),
        sa.UniqueConstraint(
            "event_id", "consumer_name", name="uq_business_event_delivery_consumer"
        ),
    )
    op.create_index(
        "ix_business_event_delivery_ready",
        "business_event_deliveries",
        ["status", "next_attempt_at", "created_at", "id"],
    )
    op.create_index(
        "ix_business_event_delivery_scope",
        "business_event_deliveries",
        ["company_id", "branch_id"],
    )
    op.create_index(
        "uq_business_event_delivery_claim_token",
        "business_event_deliveries",
        ["claim_token"],
        unique=True,
        postgresql_where=sa.text("claim_token IS NOT NULL"),
    )

    op.create_table(
        "business_event_delivery_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_event_deliveries.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_name", sa.String(160), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_sequence", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("worker_id", sa.String(120)),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_category", sa.String(40)),
        sa.Column("outcome_digest", sa.String(64)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('claimed','recovered','delivered','idempotent','retryable','terminal','replay_requested')",
            name="ck_business_event_delivery_evidence_outcome",
        ),
        sa.UniqueConstraint(
            "delivery_id",
            "evidence_sequence",
            name="uq_business_event_evidence_sequence",
        ),
    )

    op.create_table(
        "business_event_consumer_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("consumer_name", sa.String(160), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("outcome_digest", sa.String(64), nullable=False),
        sa.Column("aggregate_sequence", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "event_id", "consumer_name", name="uq_business_event_consumer_receipt"
        ),
    )

    op.create_index(
        "uq_business_event_replay_request",
        "business_event_delivery_evidence",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
    )

    op.create_table(
        "business_event_consumer_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_name", sa.String(160), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "consumer_name",
            "company_id",
            "entity_type",
            "entity_id",
            name="uq_business_event_consumer_cursor",
        ),
    )

    op.execute("""
        CREATE FUNCTION reject_business_event_delivery_evidence_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Business Event delivery evidence is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    for table in (
        "business_event_delivery_evidence",
        "business_event_consumer_receipts",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_business_event_delivery_evidence_mutation()"
        )


def downgrade() -> None:
    for table in (
        "business_event_consumer_receipts",
        "business_event_delivery_evidence",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute(
        "DROP FUNCTION IF EXISTS reject_business_event_delivery_evidence_mutation()"
    )
    op.drop_table("business_event_consumer_cursors")
    op.drop_table("business_event_consumer_receipts")
    op.execute("DROP INDEX IF EXISTS uq_business_event_replay_request")
    op.drop_table("business_event_delivery_evidence")
    op.drop_index(
        "uq_business_event_delivery_claim_token", table_name="business_event_deliveries"
    )
    op.drop_index(
        "ix_business_event_delivery_scope", table_name="business_event_deliveries"
    )
    op.drop_index(
        "ix_business_event_delivery_ready", table_name="business_event_deliveries"
    )
    op.drop_table("business_event_deliveries")
