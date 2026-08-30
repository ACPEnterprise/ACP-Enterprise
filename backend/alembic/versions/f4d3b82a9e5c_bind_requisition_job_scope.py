"""bind requisition Job provenance to Company and Branch

Revision ID: f4d3b82a9e5c
Revises: e3c2a71f8d4b
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f4d3b82a9e5c"
down_revision: str | Sequence[str] | None = "e3c2a71f8d4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_purchasing_requisition_job",
        "purchasing_requisitions",
        "jobs",
        ["company_id", "branch_id", "job_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_purchasing_requisition_job",
        "purchasing_requisitions",
        type_="foreignkey",
    )
