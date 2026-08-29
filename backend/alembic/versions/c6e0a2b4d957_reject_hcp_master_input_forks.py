"""Reject competing master inputs for one SOURCE.4 package and scope.

Revision ID: c6e0a2b4d957
Revises: b5d9f1a3c846
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c6e0a2b4d957"
down_revision: str | Sequence[str] | None = "b5d9f1a3c846"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_hcp_master_package_scope",
        "hcp_migration_master_runs",
        ["company_id", "branch_id", "package_digest"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_hcp_master_package_scope", "hcp_migration_master_runs", type_="unique"
    )
