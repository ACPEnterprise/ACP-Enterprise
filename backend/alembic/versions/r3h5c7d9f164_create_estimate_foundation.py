"""create estimate foundation

Revision ID: r3h5c7d9f164
Revises: q2g4b6d8e053
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "r3h5c7d9f164"
down_revision: str | None = "q2g4b6d8e053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_price_book_snapshots_company_id",
        "price_book_commercial_snapshots",
        ["company_id", "id"],
    )
    op.create_table(
        "estimate_number_sequences",
        sa.Column("company_id", UUID, primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "last_value >= 0", name="ck_estimate_number_sequences_value"
        ),
    )
    op.create_table(
        "estimate_proposals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=False),
        sa.Column("service_location_id", UUID),
        sa.Column("estimate_number", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("acceptance_status", sa.String(24), nullable=False),
        sa.Column("current_revision_id", UUID),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_estimates_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_estimates_customer_location",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "estimate_number ~ '^EST-[0-9]{6,}$'", name="ck_estimates_number"
        ),
        sa.CheckConstraint(
            "status IN ('draft','proposed','accepted','declined','expired','cancelled')",
            name="ck_estimates_status",
        ),
        sa.CheckConstraint(
            "acceptance_status IN ('not_requested','pending','accepted','declined','expired','withdrawn')",
            name="ck_estimates_acceptance_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_estimates_version"),
        sa.UniqueConstraint(
            "company_id", "estimate_number", name="uq_estimates_company_number"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_estimate_proposals_company_id"
        ),
    )
    op.create_index(
        "ix_estimates_company_branch_status",
        "estimate_proposals",
        ["company_id", "branch_id", "status"],
    )
    op.create_table(
        "estimate_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("estimate_id", UUID, nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("proposal_title", sa.String(240), nullable=False),
        sa.Column("customer_message", sa.Text()),
        sa.Column("terms", sa.Text()),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_revisions_estimate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("revision_number >= 1", name="ck_estimate_revisions_number"),
        sa.CheckConstraint(
            "status IN ('draft','issued','superseded','withdrawn')",
            name="ck_estimate_revisions_status",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_estimate_revisions_currency"
        ),
        sa.CheckConstraint(
            "subtotal_amount >= 0 AND total_amount >= 0",
            name="ck_estimate_revisions_amounts",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_estimate_revisions_expiry",
        ),
        sa.UniqueConstraint(
            "company_id",
            "estimate_id",
            "revision_number",
            name="uq_estimate_revisions_number",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_estimate_revisions_company_id"
        ),
    )
    op.create_index(
        "ix_estimate_revisions_estimate",
        "estimate_revisions",
        ["company_id", "estimate_id", "revision_number"],
    )
    op.create_foreign_key(
        "fk_estimates_current_revision",
        "estimate_proposals",
        "estimate_revisions",
        ["company_id", "current_revision_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "estimate_revision_line_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("revision_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_lines_revision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("position >= 1", name="ck_estimate_lines_position"),
        sa.CheckConstraint(
            "quantity > 0 AND unit_price >= 0 AND line_total >= 0",
            name="ck_estimate_lines_amounts",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_estimate_lines_currency"
        ),
        sa.UniqueConstraint(
            "company_id", "revision_id", "position", name="uq_estimate_lines_position"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_estimate_lines_company_id"),
    )
    op.create_table(
        "estimate_commercial_snapshot_references",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("revision_id", UUID, nullable=False),
        sa.Column("line_item_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_snapshot_refs_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "line_item_id"],
            [
                "estimate_revision_line_items.company_id",
                "estimate_revision_line_items.id",
            ],
            name="fk_estimate_snapshot_refs_line",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "snapshot_id"],
            [
                "price_book_commercial_snapshots.company_id",
                "price_book_commercial_snapshots.id",
            ],
            name="fk_estimate_snapshot_refs_snapshot",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "snapshot_digest ~ '^[0-9a-f]{64}$'",
            name="ck_estimate_snapshot_refs_digest",
        ),
        sa.UniqueConstraint(
            "company_id", "line_item_id", name="uq_estimate_snapshot_refs_line"
        ),
        sa.UniqueConstraint(
            "company_id",
            "revision_id",
            "snapshot_id",
            name="uq_estimate_snapshot_refs_revision_snapshot",
        ),
    )
    op.create_table(
        "estimate_lifecycle_history",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("estimate_id", UUID, nullable=False),
        sa.Column("from_status", sa.String(24)),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("from_acceptance_status", sa.String(24)),
        sa.Column("to_acceptance_status", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_estimate_history_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_history_estimate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("version >= 1", name="ck_estimate_history_version"),
        sa.UniqueConstraint(
            "company_id", "estimate_id", "version", name="uq_estimate_history_version"
        ),
    )
    op.create_index(
        "ix_estimate_history_timeline",
        "estimate_lifecycle_history",
        ["company_id", "estimate_id", "occurred_at"],
    )
    op.execute("""
        CREATE FUNCTION reject_estimate_evidence_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'estimate revision evidence is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    for table in (
        "estimate_revisions",
        "estimate_revision_line_items",
        "estimate_commercial_snapshot_references",
        "estimate_lifecycle_history",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_estimate_evidence_mutation()"
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_estimates_current_revision", "estimate_proposals", type_="foreignkey"
    )
    for table in (
        "estimate_lifecycle_history",
        "estimate_commercial_snapshot_references",
        "estimate_revision_line_items",
        "estimate_revisions",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION reject_estimate_evidence_mutation()")
    op.drop_table("estimate_lifecycle_history")
    op.drop_table("estimate_commercial_snapshot_references")
    op.drop_table("estimate_revision_line_items")
    op.drop_table("estimate_revisions")
    op.drop_table("estimate_proposals")
    op.drop_table("estimate_number_sequences")
    op.drop_constraint(
        "uq_price_book_snapshots_company_id",
        "price_book_commercial_snapshots",
        type_="unique",
    )
