"""Protect Luminary tenant scope and successor lineage.

Revision ID: l0j9h48g5e1c
Revises: k9i8g37f4d0b
"""

from collections.abc import Sequence

from alembic import op

revision: str = "l0j9h48g5e1c"
down_revision: str | Sequence[str] | None = "k9i8g37f4d0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "luminary_findings_branch_id_fkey", "luminary_findings", type_="foreignkey"
    )
    op.drop_constraint(
        "luminary_findings_supersedes_finding_id_fkey",
        "luminary_findings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "luminary_briefings_branch_id_fkey", "luminary_briefings", type_="foreignkey"
    )
    op.drop_constraint(
        "luminary_briefings_supersedes_briefing_id_fkey",
        "luminary_briefings",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_luminary_finding_company_branch",
        "luminary_findings",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_luminary_finding_company_supersedes",
        "luminary_findings",
        "luminary_findings",
        ["company_id", "supersedes_finding_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_luminary_briefing_company_branch",
        "luminary_briefings",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_luminary_briefing_company_supersedes",
        "luminary_briefings",
        "luminary_briefings",
        ["company_id", "supersedes_briefing_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_luminary_briefing_company_supersedes",
        "luminary_briefings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_luminary_briefing_company_branch", "luminary_briefings", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_luminary_finding_company_supersedes",
        "luminary_findings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_luminary_finding_company_branch", "luminary_findings", type_="foreignkey"
    )
    op.create_foreign_key(
        "luminary_briefings_supersedes_briefing_id_fkey",
        "luminary_briefings",
        "luminary_briefings",
        ["supersedes_briefing_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "luminary_briefings_branch_id_fkey",
        "luminary_briefings",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "luminary_findings_supersedes_finding_id_fkey",
        "luminary_findings",
        "luminary_findings",
        ["supersedes_finding_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "luminary_findings_branch_id_fkey",
        "luminary_findings",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
