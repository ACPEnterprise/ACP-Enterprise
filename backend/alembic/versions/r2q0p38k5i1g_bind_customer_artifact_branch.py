"""Bind Customer Migration source artifacts to tenant Branch authority.

Revision ID: r2q0p38k5i1g
Revises: q1p9o27j4h0f
"""

from collections.abc import Sequence

from alembic import op

revision: str = "r2q0p38k5i1g"
down_revision: str | Sequence[str] | None = "q1p9o27j4h0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "customer_migration_source_artifacts_branch_id_fkey",
        "customer_migration_source_artifacts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_customer_source_artifact_branch_scope",
        "customer_migration_source_artifacts",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_customer_source_artifact_branch_scope",
        "customer_migration_source_artifacts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "customer_migration_source_artifacts_branch_id_fkey",
        "customer_migration_source_artifacts",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
