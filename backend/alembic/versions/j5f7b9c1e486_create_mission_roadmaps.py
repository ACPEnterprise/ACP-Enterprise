"""Create Mission Control roadmaps and milestone dispatch.

Revision ID: j5f7b9c1e486
Revises: i4e6a8b0d375
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "j5f7b9c1e486"
down_revision: str | None = "i4e6a8b0d375"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_roadmaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("repository_key", sa.String(100), nullable=False),
        sa.Column("expected_branch", sa.String(255), nullable=False),
        sa.Column("expected_head", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('active','completed','archived')",
            name="ck_engineering_roadmap_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_engineering_roadmap_version"),
        sa.CheckConstraint(
            "expected_head ~ '^[0-9a-f]{40}$'", name="ck_engineering_roadmap_head"
        ),
    )
    op.create_index(
        "ix_engineering_roadmap_company_status",
        "engineering_roadmaps",
        ["company_id", "status", "updated_at"],
    )
    op.create_table(
        "engineering_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("authority", postgresql.JSONB(), nullable=False),
        sa.Column("constraints", postgresql.JSONB(), nullable=False),
        sa.Column("validation", postgresql.JSONB(), nullable=False),
        sa.Column("deliverables", postgresql.JSONB(), nullable=False),
        sa.Column("stop_conditions", postgresql.JSONB(), nullable=False),
        sa.Column("expected_completion_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("definition_approved", sa.Boolean(), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["roadmap_id"], ["engineering_roadmaps.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "roadmap_id", "position", name="uq_engineering_milestone_position"
        ),
        sa.CheckConstraint("position >= 1", name="ck_engineering_milestone_position"),
        sa.CheckConstraint("version >= 1", name="ck_engineering_milestone_version"),
        sa.CheckConstraint(
            "status IN ('planned','ready','running','waiting_review','waiting_approval','blocked','completed','paused','cancelled','skipped','archived')",
            name="ck_engineering_milestone_status",
        ),
    )
    op.create_index(
        "ix_engineering_milestone_company_status",
        "engineering_milestones",
        ["company_id", "status", "updated_at"],
    )
    op.create_table(
        "engineering_milestone_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("prior_status", sa.String(24)),
        sa.Column("new_status", sa.String(24), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason", sa.String(240)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["roadmap_id"], ["engineering_roadmaps.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["engineering_milestones.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_engineering_milestone_event_order",
        "engineering_milestone_events",
        ["company_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("engineering_milestone_events")
    op.drop_table("engineering_milestones")
    op.drop_table("engineering_roadmaps")
