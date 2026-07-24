"""create engineering execution bridge

Revision ID: a1c3e5f7b902
Revises: f7a9c2e4d681
Create Date: 2026-07-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1c3e5f7b902"
down_revision: str | None = "f7a9c2e4d681"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ecid", sa.String(length=32), nullable=False),
        sa.Column("instruction_digest", sa.String(length=128), nullable=False),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("provider_identifier", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "evidence_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "validation_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "output_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("failure_classification", sa.String(length=100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(provider_identifier)) > 0",
            name="ck_engineering_executions_provider_not_blank",
        ),
        sa.CheckConstraint(
            "state IN ('execution_not_connected','queued','starting','running',"
            "'completed','failed','cancelled')",
            name="ck_engineering_executions_state",
        ),
        sa.CheckConstraint(
            "status IN ('disconnected','queued','starting','running','succeeded',"
            "'failed','cancelled')",
            name="ck_engineering_executions_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_engineering_executions_version"),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_engineering_executions_updated_at",
        ),
        sa.CheckConstraint(
            "started_at IS NULL AND finished_at IS NULL "
            "OR started_at IS NOT NULL AND "
            "(finished_at IS NULL OR finished_at >= started_at)",
            name="ck_engineering_executions_timestamps",
        ),
        sa.CheckConstraint(
            "failure_classification IS NULL OR "
            "length(btrim(failure_classification)) > 0",
            name="ck_engineering_executions_failure_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_engineering_executions_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "command_id", "ecid", "instruction_digest"],
            [
                "engineering_commands.company_id",
                "engineering_commands.id",
                "engineering_commands.ecid",
                "engineering_commands.instruction_digest",
            ],
            name="fk_engineering_executions_command",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_executions_requesting_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_executions"),
        sa.UniqueConstraint(
            "company_id",
            "command_id",
            name="uq_engineering_executions_company_command",
        ),
    )
    op.create_index(
        "ix_engineering_executions_company_created",
        "engineering_executions",
        ["company_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_engineering_executions_company_state",
        "engineering_executions",
        ["company_id", "state", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_engineering_executions_command",
        "engineering_executions",
        ["company_id", "command_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_engineering_executions_command", table_name="engineering_executions"
    )
    op.drop_index(
        "ix_engineering_executions_company_state",
        table_name="engineering_executions",
    )
    op.drop_index(
        "ix_engineering_executions_company_created",
        table_name="engineering_executions",
    )
    op.drop_table("engineering_executions")
