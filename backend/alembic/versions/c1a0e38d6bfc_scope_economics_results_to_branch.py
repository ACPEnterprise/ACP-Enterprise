"""scope economics results to Company Branch authority

Revision ID: c1a0e38d6bfc
Revises: b0ff279c5aeb
Create Date: 2026-08-30 14:05:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c1a0e38d6bfc"
down_revision: str | Sequence[str] | None = "b0ff279c5aeb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_eco_profitability_result_company_branch",
        "economics_profitability_results",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_eco_profitability_result_company_branch",
        "economics_profitability_results",
        type_="foreignkey",
    )
