"""Bind Timekeeping and Economics predecessor authority.

Revision ID: n8l7m26i3g9e
Revises: m7k6l15h2f8d
"""

from collections.abc import Sequence

from alembic import op

revision: str = "n8l7m26i3g9e"
down_revision: str | Sequence[str] | None = "m7k6l15h2f8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_time_entry_revision_predecessor_scope",
        "timekeeping_entry_revisions",
        ["company_id", "entry_id", "id"],
    )
    op.drop_constraint(
        "timekeeping_entry_revisions_supersedes_revision_id_fkey",
        "timekeeping_entry_revisions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_time_entry_revision_predecessor_scope",
        "timekeeping_entry_revisions",
        "timekeeping_entry_revisions",
        ["company_id", "entry_id", "supersedes_revision_id"],
        ["company_id", "entry_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "economics_company_policy_versions_supersedes_policy_id_fkey",
        "economics_company_policy_versions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_eco_policy_predecessor_scope",
        "economics_company_policy_versions",
        "economics_company_policy_versions",
        ["company_id", "supersedes_policy_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_unique_constraint(
        "uq_eco_policy_gap_company",
        "economics_company_policy_gaps",
        ["company_id", "id"],
    )
    op.drop_constraint(
        "economics_policy_gap_closures_gap_id_fkey",
        "economics_policy_gap_closures",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_eco_gap_closure_gap_scope",
        "economics_policy_gap_closures",
        "economics_company_policy_gaps",
        ["company_id", "gap_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_eco_gap_closure_gap_scope",
        "economics_policy_gap_closures",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "economics_policy_gap_closures_gap_id_fkey",
        "economics_policy_gap_closures",
        "economics_company_policy_gaps",
        ["gap_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_eco_policy_gap_company",
        "economics_company_policy_gaps",
        type_="unique",
    )

    op.drop_constraint(
        "fk_eco_policy_predecessor_scope",
        "economics_company_policy_versions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "economics_company_policy_versions_supersedes_policy_id_fkey",
        "economics_company_policy_versions",
        "economics_company_policy_versions",
        ["supersedes_policy_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_time_entry_revision_predecessor_scope",
        "timekeeping_entry_revisions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "timekeeping_entry_revisions_supersedes_revision_id_fkey",
        "timekeeping_entry_revisions",
        "timekeeping_entry_revisions",
        ["supersedes_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_time_entry_revision_predecessor_scope",
        "timekeeping_entry_revisions",
        type_="unique",
    )
