"""create bounded repository operations

Revision ID: d3f5a7c9e162
Revises: c2f4a6b8d051
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3f5a7c9e162"
down_revision: str | None = "c2f4a6b8d051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = (
    "'requested','reserved','executing','succeeded','failed','reconciliation_required'"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_repository_authorizations_operation",
        "engineering_repository_authorizations",
        type_="check",
    )
    op.execute(
        "UPDATE engineering_repository_authorizations "
        "SET operation_type = 'create_commit' WHERE operation_type = 'commit'"
    )
    op.create_check_constraint(
        "ck_repository_authorizations_operation",
        "engineering_repository_authorizations",
        "operation_type IN ('create_commit')",
    )
    op.create_table(
        "engineering_repository_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authorization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("operation_type", sa.String(30), nullable=False),
        sa.Column("commit_subject", sa.String(120), nullable=False),
        sa.Column("expected_branch", sa.String(255), nullable=False),
        sa.Column("expected_base_commit", sa.String(40), nullable=False),
        sa.Column("file_boundary", postgresql.JSONB(), nullable=False),
        sa.Column("boundary_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("resulting_commit_sha", sa.String(40)),
        sa.Column("failure_classification", sa.String(80)),
        sa.Column("failure_detail", sa.String(240)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True)),
        sa.Column("execution_started_at", sa.DateTime(timezone=True)),
        sa.Column("succeeded_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("reconciliation_required_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation_type = 'create_commit'",
            name="ck_repository_operations_type",
        ),
        sa.CheckConstraint(
            f"state IN ({STATES})",
            name="ck_repository_operations_state",
        ),
        sa.CheckConstraint(
            "expected_base_commit ~ '^[0-9a-f]{40}$'",
            name="ck_repository_operations_base_commit",
        ),
        sa.CheckConstraint(
            "resulting_commit_sha IS NULL OR resulting_commit_sha ~ '^[0-9a-f]{40}$'",
            name="ck_repository_operations_result_sha",
        ),
        sa.CheckConstraint(
            "length(boundary_digest) = 64",
            name="ck_repository_operations_boundary_digest",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(file_boundary) > 0",
            name="ck_repository_operations_boundary",
        ),
        sa.CheckConstraint(
            "length(btrim(commit_subject)) BETWEEN 1 AND 120 "
            "AND commit_subject !~ '[\\n\\r]'",
            name="ck_repository_operations_subject",
        ),
        sa.CheckConstraint("version >= 1", name="ck_repository_operations_version"),
        sa.CheckConstraint(
            "(state = 'succeeded') = "
            "(succeeded_at IS NOT NULL AND resulting_commit_sha IS NOT NULL)",
            name="ck_repository_operations_succeeded",
        ),
        sa.CheckConstraint(
            "(state = 'failed') = (failed_at IS NOT NULL)",
            name="ck_repository_operations_failed",
        ),
        sa.CheckConstraint(
            "(state = 'reconciliation_required') = "
            "(reconciliation_required_at IS NOT NULL)",
            name="ck_repository_operations_reconciliation",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "authorization_id"],
            [
                "engineering_repository_authorizations.company_id",
                "engineering_repository_authorizations.id",
            ],
            name="fk_repository_operations_authorization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["engineering_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["review_decision_id"],
            ["engineering_execution_review_decisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_operations_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "authorization_id",
            name="uq_repository_operations_authorization",
        ),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_repository_operations_idempotency",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_repository_operations_company_id"
        ),
    )
    op.create_index(
        "ix_repository_operations_company_state",
        "engineering_repository_operations",
        ["company_id", "state", "updated_at", "id"],
    )
    op.create_index(
        "ix_repository_operations_company_command",
        "engineering_repository_operations",
        ["company_id", "command_id", "requested_at", "id"],
    )
    op.create_table(
        "engineering_repository_operation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resulting_commit_sha", sa.String(40)),
        sa.Column("failure_classification", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN "
            "('requested','reserved','started','succeeded','failed',"
            "'reconciliation_required')",
            name="ck_repository_operation_events_type",
        ),
        sa.CheckConstraint(
            f"state IN ({STATES})",
            name="ck_repository_operation_events_state",
        ),
        sa.CheckConstraint(
            "resulting_commit_sha IS NULL OR resulting_commit_sha ~ '^[0-9a-f]{40}$'",
            name="ck_repository_operation_events_result_sha",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_repository_operation_events_version"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "operation_id"],
            [
                "engineering_repository_operations.company_id",
                "engineering_repository_operations.id",
            ],
            name="fk_repository_operation_events_operation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_repository_operation_events_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "operation_id",
            "version",
            "event_type",
            name="uq_repository_operation_events_version",
        ),
    )
    op.create_index(
        "ix_repository_operation_events_company_created",
        "engineering_repository_operation_events",
        ["company_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_repository_operation_events_company_created",
        table_name="engineering_repository_operation_events",
    )
    op.drop_table("engineering_repository_operation_events")
    op.drop_index(
        "ix_repository_operations_company_command",
        table_name="engineering_repository_operations",
    )
    op.drop_index(
        "ix_repository_operations_company_state",
        table_name="engineering_repository_operations",
    )
    op.drop_table("engineering_repository_operations")
    op.drop_constraint(
        "ck_repository_authorizations_operation",
        "engineering_repository_authorizations",
        type_="check",
    )
    op.execute(
        "UPDATE engineering_repository_authorizations "
        "SET operation_type = 'commit' WHERE operation_type = 'create_commit'"
    )
    op.create_check_constraint(
        "ck_repository_authorizations_operation",
        "engineering_repository_authorizations",
        "operation_type IN ('commit')",
    )
