"""version procurement match evidence

Revision ID: 17g2i67862h6
Revises: 16f1h56751g5
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "17g2i67862h6"
down_revision: str | Sequence[str] | None = "16f1h56751g5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "procurement_three_way_matches",
        sa.Column("source_evidence_digest", sa.String(64), nullable=True),
    )
    op.add_column(
        "procurement_three_way_matches",
        sa.Column("evaluation_sequence", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "procurement_three_way_matches",
        sa.Column("supersedes_match_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "procurement_three_way_matches",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE procurement_three_way_matches "
        "SET source_evidence_digest = evidence_digest "
        "WHERE source_evidence_digest IS NULL"
    )
    op.alter_column(
        "procurement_three_way_matches", "source_evidence_digest", nullable=False
    )
    op.drop_constraint(
        "uq_procurement_match_bill",
        "procurement_three_way_matches",
        type_="unique",
    )
    op.create_foreign_key(
        "fk_procurement_match_supersedes",
        "procurement_three_way_matches",
        "procurement_three_way_matches",
        ["company_id", "supersedes_match_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_procurement_match_bill_sequence",
        "procurement_three_way_matches",
        ["company_id", "vendor_bill_id", "evaluation_sequence"],
    )
    op.create_index(
        "uq_procurement_match_active_bill",
        "procurement_three_way_matches",
        ["company_id", "vendor_bill_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.alter_column(
        "procurement_three_way_matches",
        "evaluation_sequence",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_procurement_match_active_bill",
        table_name="procurement_three_way_matches",
    )
    op.drop_constraint(
        "uq_procurement_match_bill_sequence",
        "procurement_three_way_matches",
        type_="unique",
    )
    op.drop_constraint(
        "fk_procurement_match_supersedes",
        "procurement_three_way_matches",
        type_="foreignkey",
    )
    op.create_unique_constraint(
        "uq_procurement_match_bill",
        "procurement_three_way_matches",
        ["company_id", "vendor_bill_id"],
    )
    op.drop_column("procurement_three_way_matches", "superseded_at")
    op.drop_column("procurement_three_way_matches", "supersedes_match_id")
    op.drop_column("procurement_three_way_matches", "evaluation_sequence")
    op.drop_column("procurement_three_way_matches", "source_evidence_digest")
