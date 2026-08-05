"""create estimate approval workflow

Revision ID: s4i6d8e0a275
Revises: r3h5c7d9f164
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "s4i6d8e0a275"
down_revision: str | None = "r3h5c7d9f164"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("ck_estimates_status", "estimate_proposals", type_="check")
    op.create_check_constraint(
        "ck_estimates_status",
        "estimate_proposals",
        "status IN ('draft','sent','viewed','approved','rejected','expired',"
        "'proposed','accepted','declined','cancelled')",
    )
    op.drop_constraint(
        "ck_estimates_acceptance_status", "estimate_proposals", type_="check"
    )
    op.create_check_constraint(
        "ck_estimates_acceptance_status",
        "estimate_proposals",
        "acceptance_status IN ('not_requested','pending','approved','rejected',"
        "'expired','accepted','declined','withdrawn')",
    )
    op.add_column(
        "estimate_revisions", sa.Column("parent_revision_id", UUID, nullable=True)
    )
    op.create_foreign_key(
        "fk_estimate_revisions_parent",
        "estimate_revisions",
        "estimate_revisions",
        ["company_id", "parent_revision_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "estimate_customer_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("estimate_id", UUID, nullable=False),
        sa.Column("revision_id", UUID, nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("customer_name", sa.String(240), nullable=False),
        sa.Column("customer_email", sa.String(320)),
        sa.Column("customer_comment", sa.Text()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("evidence_reference", sa.String(240)),
        sa.Column("recorded_by_user_id", UUID, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_customer_decisions_estimate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_customer_decisions_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_estimate_customer_decisions_type",
        ),
        sa.CheckConstraint(
            "(decision = 'approved' AND rejection_reason IS NULL) OR "
            "(decision = 'rejected' AND rejection_reason IS NOT NULL "
            "AND length(btrim(rejection_reason)) > 0)",
            name="ck_estimate_customer_decisions_reason",
        ),
        sa.UniqueConstraint(
            "company_id",
            "revision_id",
            name="uq_estimate_customer_decisions_revision",
        ),
    )
    op.create_index(
        "ix_estimate_customer_decisions_estimate",
        "estimate_customer_decisions",
        ["company_id", "estimate_id", "occurred_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_estimate_customer_decisions_immutable "
        "BEFORE UPDATE OR DELETE ON estimate_customer_decisions FOR EACH ROW "
        "EXECUTE FUNCTION reject_estimate_evidence_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_estimate_customer_decisions_immutable "
        "ON estimate_customer_decisions"
    )
    op.drop_table("estimate_customer_decisions")
    op.drop_constraint(
        "fk_estimate_revisions_parent", "estimate_revisions", type_="foreignkey"
    )
    op.drop_column("estimate_revisions", "parent_revision_id")
    op.drop_constraint(
        "ck_estimates_acceptance_status", "estimate_proposals", type_="check"
    )
    op.create_check_constraint(
        "ck_estimates_acceptance_status",
        "estimate_proposals",
        "acceptance_status IN "
        "('not_requested','pending','accepted','declined','expired','withdrawn')",
    )
    op.drop_constraint("ck_estimates_status", "estimate_proposals", type_="check")
    op.create_check_constraint(
        "ck_estimates_status",
        "estimate_proposals",
        "status IN ('draft','proposed','accepted','declined','expired','cancelled')",
    )
