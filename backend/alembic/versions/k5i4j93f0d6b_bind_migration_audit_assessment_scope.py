"""Bind Migration audit summaries to exact assessment scope.

Revision ID: k5i4j93f0d6b
Revises: j4h3i82e9c5a
"""

from collections.abc import Sequence

from alembic import op

revision: str = "k5i4j93f0d6b"
down_revision: str | Sequence[str] | None = "j4h3i82e9c5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_migration_cutover_assessment_scope",
        "operational_migration_cutover_assessments",
        ["id", "company_id", "branch_id"],
    )
    op.drop_constraint(
        "operational_migration_audit_summaries_assessment_id_fkey",
        "operational_migration_audit_summaries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_migration_audit_summary_assessment_scope",
        "operational_migration_audit_summaries",
        "operational_migration_cutover_assessments",
        ["assessment_id", "company_id", "branch_id"],
        ["id", "company_id", "branch_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_migration_audit_summary_assessment_scope",
        "operational_migration_audit_summaries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "operational_migration_audit_summaries_assessment_id_fkey",
        "operational_migration_audit_summaries",
        "operational_migration_cutover_assessments",
        ["assessment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_migration_cutover_assessment_scope",
        "operational_migration_cutover_assessments",
        type_="unique",
    )
