"""create owner workstream controls

Revision ID: f0a2c4e6b831
Revises: e6b2c8d0f374
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f0a2c4e6b831"
down_revision = "e6b2c8d0f374"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engineering_workstream_controls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("desired_state", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=240)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "desired_state IN ('active','paused','cancelled')",
            name="ck_workstream_controls_desired_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_workstream_controls_version"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_workstream_controls_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["command_id"],
            ["engineering_commands.id"],
            name="fk_workstream_controls_command",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_workstream_controls_actor_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "command_id", name="uq_workstream_controls_command"
        ),
    )


def downgrade() -> None:
    op.drop_table("engineering_workstream_controls")
