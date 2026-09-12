"""Create governed break-even policy operation events.

Revision ID: g7i9k1m3o5q7
Revises: f6h8j0l2n4p6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "g7i9k1m3o5q7"
down_revision = "f6h8j0l2n4p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "economics_break_even_policy_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_key", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column(
            "value_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approver_role", sa.String(length=30), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("provenance_digest", sa.String(length=64), nullable=False),
        sa.Column("policy_digest", sa.String(length=64), nullable=False),
        sa.Column("supersedes_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prior_event_digest", sa.String(length=64), nullable=True),
        sa.Column("event_digest", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('DRAFT','AWAITING_APPROVAL','APPROVED','SUPERSEDED')",
            name="ck_eco_be_policy_event_state",
        ),
        sa.CheckConstraint("policy_version >= 1", name="ck_eco_be_policy_version"),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_eco_be_policy_interval",
        ),
        sa.CheckConstraint(
            "scope_id = COALESCE(branch_id, company_id)",
            name="ck_eco_be_policy_scope_identity",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_eco_be_policy_branch_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_digest", name="uq_eco_be_policy_event_digest"),
        sa.UniqueConstraint(
            "company_id",
            "scope_id",
            "family_key",
            "policy_version",
            "state",
            name="uq_eco_be_policy_version_state",
        ),
    )
    op.create_index(
        "ix_eco_be_policy_resolution",
        "economics_break_even_policy_events",
        ["company_id", "scope_id", "family_key", "state", "effective_start"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION reject_break_even_policy_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'governed break-even policy events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eco_be_policy_event_immutable
        BEFORE UPDATE OR DELETE ON economics_break_even_policy_events
        FOR EACH ROW EXECUTE FUNCTION reject_break_even_policy_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_eco_be_policy_event_immutable "
        "ON economics_break_even_policy_events"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_break_even_policy_event_mutation()")
    op.drop_index(
        "ix_eco_be_policy_resolution", table_name="economics_break_even_policy_events"
    )
    op.drop_table("economics_break_even_policy_events")
