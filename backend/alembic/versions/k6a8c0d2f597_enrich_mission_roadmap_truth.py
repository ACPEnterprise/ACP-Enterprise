"""Enrich Mission Control roadmap truth.

Revision ID: k6a8c0d2f597
Revises: j5f7b9c1e486
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "k6a8c0d2f597"
down_revision: str | None = "j5f7b9c1e486"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "engineering_milestones",
        sa.Column("owning_workstream", sa.String(100), nullable=True),
    )
    op.add_column(
        "engineering_milestones",
        sa.Column("owning_branch", sa.String(255), nullable=True),
    )
    op.add_column(
        "engineering_milestones",
        sa.Column(
            "dependencies", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
    )
    op.add_column(
        "engineering_milestones",
        sa.Column("external_evidence", sa.Text(), nullable=True),
    )
    op.add_column(
        "engineering_milestones",
        sa.Column(
            "requested_code_changes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.execute(
        "UPDATE engineering_milestones AS milestone "
        "SET owning_workstream = roadmap.title, "
        "owning_branch = roadmap.expected_branch "
        "FROM engineering_roadmaps AS roadmap "
        "WHERE milestone.roadmap_id = roadmap.id"
    )
    op.alter_column("engineering_milestones", "owning_workstream", nullable=False)
    op.alter_column("engineering_milestones", "owning_branch", nullable=False)
    op.drop_constraint(
        "ck_engineering_milestone_status",
        "engineering_milestones",
        type_="check",
    )
    op.create_check_constraint(
        "ck_engineering_milestone_status",
        "engineering_milestones",
        "status IN ('draft','planned','ready','running','externally_running','waiting_review','waiting_approval','blocked','completed','paused','cancelled','skipped','archived')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE engineering_milestones SET status = 'planned' "
        "WHERE status IN ('draft','externally_running')"
    )
    op.drop_constraint(
        "ck_engineering_milestone_status",
        "engineering_milestones",
        type_="check",
    )
    op.create_check_constraint(
        "ck_engineering_milestone_status",
        "engineering_milestones",
        "status IN ('planned','ready','running','waiting_review','waiting_approval','blocked','completed','paused','cancelled','skipped','archived')",
    )
    op.drop_column("engineering_milestones", "external_evidence")
    op.drop_column("engineering_milestones", "requested_code_changes")
    op.drop_column("engineering_milestones", "dependencies")
    op.drop_column("engineering_milestones", "owning_branch")
    op.drop_column("engineering_milestones", "owning_workstream")
