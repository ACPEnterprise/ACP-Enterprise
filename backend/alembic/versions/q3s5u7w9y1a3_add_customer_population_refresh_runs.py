"""add Customer population refresh run ledger

Revision ID: q3s5u7w9y1a3
Revises: p2r4t6v8x0z2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "q3s5u7w9y1a3"
down_revision: str | Sequence[str] | None = "p2r4t6v8x0z2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_population_refresh_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("bound_count", sa.Integer(), nullable=False),
        sa.Column("held_count", sa.Integer(), nullable=False),
        sa.Column("ambiguous_count", sa.Integer(), nullable=False),
        sa.Column("unexplained_count", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "total_count >= 0 AND bound_count >= 0 AND held_count >= 0 "
            "AND ambiguous_count >= 0 AND unexplained_count >= 0",
            name="ck_customer_population_refresh_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "total_count = bound_count + held_count + ambiguous_count "
            "+ unexplained_count",
            name="ck_customer_population_refresh_counts_reconcile",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_population_refresh_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_population_refresh_scope",
        "customer_population_refresh_runs",
        ["company_id", "branch_id", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_population_refresh_scope",
        table_name="customer_population_refresh_runs",
    )
    op.drop_table("customer_population_refresh_runs")
