"""create scheduler delegations

Revision ID: b2d4f6h8j0l2
Revises: n0p8r16g3t9u
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b2d4f6h8j0l2"
down_revision = "n0p8r16g3t9u"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engineering_scheduler_delegations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("queue_id", sa.String(80), nullable=False),
        sa.Column("queue_fingerprint", sa.String(64), nullable=False),
        sa.Column("authority_sha", sa.String(40), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column(
            "activated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("authorization_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("ended_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("end_reason", sa.String(240)),
        sa.ForeignKeyConstraint(
            ["activated_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("queue_fingerprint ~ '^[0-9a-f]{64}$'"),
        sa.CheckConstraint("authority_sha ~ '^[0-9a-f]{40}$'"),
        sa.CheckConstraint("state IN ('active','revoked','exhausted','paused_p0')"),
        sa.CheckConstraint("expires_at > activated_at"),
        sa.CheckConstraint("expires_at <= activated_at + interval '72 hours'"),
    )
    op.create_index(
        "uq_scheduler_delegation_active_company",
        "engineering_scheduler_delegations",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.add_column(
        "engineering_commands",
        sa.Column("scheduler_delegation_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_engineering_commands_scheduler_delegation",
        "engineering_commands",
        "engineering_scheduler_delegations",
        ["scheduler_delegation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "engineering_executions",
        sa.Column("scheduler_delegation_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_engineering_executions_scheduler_delegation",
        "engineering_executions",
        "engineering_scheduler_delegations",
        ["scheduler_delegation_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_engineering_executions_scheduler_delegation",
        "engineering_executions",
        type_="foreignkey",
    )
    op.drop_column("engineering_executions", "scheduler_delegation_id")
    op.drop_constraint(
        "fk_engineering_commands_scheduler_delegation",
        "engineering_commands",
        type_="foreignkey",
    )
    op.drop_column("engineering_commands", "scheduler_delegation_id")
    op.drop_index(
        "uq_scheduler_delegation_active_company",
        table_name="engineering_scheduler_delegations",
    )
    op.drop_table("engineering_scheduler_delegations")
