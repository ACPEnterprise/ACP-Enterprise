"""create branch purchasing policies

Revision ID: d1v3x5z7b942
Revises: c0t2p4r6u831
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d1v3x5z7b942"
down_revision: str | None = "c0t2p4r6u831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchasing_branch_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_available_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provenance_reference", sa.String(240), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','inactive')",
            name="ck_purchasing_branch_policy_status",
        ),
        sa.CheckConstraint(
            "target_available_quantity >= 0",
            name="ck_purchasing_branch_policy_target",
        ),
        sa.CheckConstraint("version >= 1", name="ck_purchasing_branch_policy_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_branch_policy_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_branch_policy_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_purchasing_branch_policy_company"
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "inventory_item_id",
            name="uq_purchasing_branch_policy_item",
        ),
    )
    op.create_index(
        "ix_purchasing_branch_policy_scope",
        "purchasing_branch_policies",
        ["company_id", "branch_id", "status"],
    )
    op.create_table(
        "purchasing_branch_policy_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("target_available_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provenance_reference", sa.String(240), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(evidence_digest) = 64 AND length(payload_digest) = 64",
            name="ck_purchasing_branch_policy_revision_digests",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive')",
            name="ck_purchasing_branch_policy_revision_status",
        ),
        sa.CheckConstraint(
            "target_available_quantity >= 0",
            name="ck_purchasing_branch_policy_revision_target",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "policy_id"],
            ["purchasing_branch_policies.company_id", "purchasing_branch_policies.id"],
            name="fk_purchasing_branch_policy_revision_policy",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_purchasing_branch_policy_revision_key",
        ),
        sa.UniqueConstraint(
            "company_id",
            "policy_id",
            "version",
            name="uq_purchasing_branch_policy_revision_version",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION purchasing_branch_policy_revision_immutable()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'purchasing branch policy revision evidence is immutable';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_purchasing_branch_policy_revision_immutable
        BEFORE UPDATE OR DELETE ON purchasing_branch_policy_revisions
        FOR EACH ROW EXECUTE FUNCTION purchasing_branch_policy_revision_immutable();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_purchasing_branch_policy_revision_immutable "
        "ON purchasing_branch_policy_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS purchasing_branch_policy_revision_immutable()")
    op.drop_table("purchasing_branch_policy_revisions")
    op.drop_index(
        "ix_purchasing_branch_policy_scope",
        table_name="purchasing_branch_policies",
    )
    op.drop_table("purchasing_branch_policies")
