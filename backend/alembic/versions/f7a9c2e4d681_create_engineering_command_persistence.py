"""create engineering command persistence

Revision ID: f7a9c2e4d681
Revises: d8f2a4c6e810
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f7a9c2e4d681"
down_revision: str | None = "d8f2a4c6e810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_command_ecid_sequences",
        sa.Column("sequence_year", sa.Integer(), nullable=False, autoincrement=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sequence_year >= 2020",
            name="ck_engineering_command_ecid_sequences_year",
        ),
        sa.CheckConstraint(
            "last_value >= 0",
            name="ck_engineering_command_ecid_sequences_last_value",
        ),
        sa.PrimaryKeyConstraint(
            "sequence_year",
            name="pk_engineering_command_ecid_sequences",
        ),
    )
    op.create_table(
        "engineering_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ecid", sa.String(length=32), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("command_type", sa.String(length=80), nullable=False),
        sa.Column("owner_instruction", sa.Text(), nullable=False),
        sa.Column("instruction_digest", sa.String(length=128), nullable=False),
        sa.Column("repository_key", sa.String(length=80), nullable=False),
        sa.Column("expected_branch", sa.String(length=255), nullable=False),
        sa.Column("expected_head", sa.String(length=40), nullable=False),
        sa.Column("requested_code_changes", sa.Boolean(), nullable=False),
        sa.Column("approval_state", sa.String(length=24), nullable=False),
        sa.Column("execution_state", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_digest", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("cancellation_reason_code", sa.String(length=100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_reference", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "ecid ~ '^ECID-[0-9]{4}-[0-9]{6,}$'",
            name="ck_engineering_commands_ecid_format",
        ),
        sa.CheckConstraint(
            "length(btrim(command_type)) > 0",
            name="ck_engineering_commands_type_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(owner_instruction)) > 0",
            name="ck_engineering_commands_instruction_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(instruction_digest)) > 0",
            name="ck_engineering_commands_instruction_digest_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(repository_key)) > 0",
            name="ck_engineering_commands_repository_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(expected_branch)) > 0",
            name="ck_engineering_commands_branch_not_blank",
        ),
        sa.CheckConstraint(
            "expected_head ~ '^[0-9a-f]{40}$'",
            name="ck_engineering_commands_expected_head",
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="ck_engineering_commands_idempotency_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(request_digest)) > 0",
            name="ck_engineering_commands_request_digest_not_blank",
        ),
        sa.CheckConstraint(
            "approval_state IN "
            "('awaiting_approval','approved','rejected','canceled','expired')",
            name="ck_engineering_commands_approval_state",
        ),
        sa.CheckConstraint(
            "execution_state = 'execution_not_connected'",
            name="ck_engineering_commands_execution_state",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_engineering_commands_version",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_engineering_commands_expiration",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_engineering_commands_updated_at",
        ),
        sa.CheckConstraint(
            "(approved_at IS NULL) = (approved_by_user_id IS NULL)",
            name="ck_engineering_commands_approval_actor",
        ),
        sa.CheckConstraint(
            "approval_state <> 'approved' OR approved_at IS NOT NULL",
            name="ck_engineering_commands_approved_state",
        ),
        sa.CheckConstraint(
            "(canceled_at IS NULL) = (canceled_by_user_id IS NULL)",
            name="ck_engineering_commands_cancellation_actor",
        ),
        sa.CheckConstraint(
            "approval_state <> 'canceled' OR canceled_at IS NOT NULL",
            name="ck_engineering_commands_canceled_state",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR length(btrim(failure_code)) > 0",
            name="ck_engineering_commands_failure_not_blank",
        ),
        sa.CheckConstraint(
            "cancellation_reason_code IS NULL OR "
            "length(btrim(cancellation_reason_code)) > 0",
            name="ck_engineering_commands_cancellation_reason_not_blank",
        ),
        sa.CheckConstraint(
            "result_reference IS NULL OR length(btrim(result_reference)) > 0",
            name="ck_engineering_commands_result_reference_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_engineering_commands_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_commands_requesting_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_commands_approving_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["canceled_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_commands_canceling_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_commands"),
        sa.UniqueConstraint("ecid", name="uq_engineering_commands_ecid"),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_engineering_commands_company_idempotency",
        ),
        sa.UniqueConstraint(
            "company_id",
            "id",
            "ecid",
            "instruction_digest",
            name="uq_engineering_commands_company_id_ecid_digest",
        ),
    )
    op.create_index(
        "ix_engineering_commands_company_created",
        "engineering_commands",
        ["company_id", "created_at", "id"],
    )
    op.create_index(
        "ix_engineering_commands_company_approval",
        "engineering_commands",
        ["company_id", "approval_state", "created_at", "id"],
    )
    op.create_index(
        "ix_engineering_commands_company_execution",
        "engineering_commands",
        ["company_id", "execution_state", "created_at", "id"],
    )
    op.create_index(
        "ix_engineering_commands_company_repository",
        "engineering_commands",
        ["company_id", "repository_key", "created_at", "id"],
    )
    op.create_index(
        "ix_engineering_commands_approved_queue",
        "engineering_commands",
        [
            "company_id",
            "repository_key",
            "approved_at",
            "created_at",
            "id",
        ],
        postgresql_where=sa.text(
            "approval_state = 'approved' "
            "AND execution_state = 'execution_not_connected'"
        ),
    )
    op.create_table(
        "engineering_command_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ecid", sa.String(length=32), nullable=False),
        sa.Column("instruction_digest", sa.String(length=128), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("prior_approval_state", sa.String(length=24), nullable=True),
        sa.Column("new_approval_state", sa.String(length=24), nullable=True),
        sa.Column("prior_execution_state", sa.String(length=32), nullable=True),
        sa.Column("new_execution_state", sa.String(length=32), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ecid ~ '^ECID-[0-9]{4}-[0-9]{6,}$'",
            name="ck_engineering_command_events_ecid_format",
        ),
        sa.CheckConstraint(
            "length(btrim(instruction_digest)) > 0",
            name="ck_engineering_command_events_instruction_digest_not_blank",
        ),
        sa.CheckConstraint(
            "sequence_number >= 1",
            name="ck_engineering_command_events_sequence",
        ),
        sa.CheckConstraint(
            "length(btrim(event_type)) > 0",
            name="ck_engineering_command_events_type_not_blank",
        ),
        sa.CheckConstraint(
            "prior_approval_state IS NULL OR prior_approval_state IN "
            "('awaiting_approval','approved','rejected','canceled','expired')",
            name="ck_engineering_command_events_prior_approval",
        ),
        sa.CheckConstraint(
            "new_approval_state IS NULL OR new_approval_state IN "
            "('awaiting_approval','approved','rejected','canceled','expired')",
            name="ck_engineering_command_events_new_approval",
        ),
        sa.CheckConstraint(
            "prior_execution_state IS NULL OR "
            "prior_execution_state = 'execution_not_connected'",
            name="ck_engineering_command_events_prior_execution",
        ),
        sa.CheckConstraint(
            "new_execution_state IS NULL OR "
            "new_execution_state = 'execution_not_connected'",
            name="ck_engineering_command_events_new_execution",
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR length(btrim(reason_code)) > 0",
            name="ck_engineering_command_events_reason_not_blank",
        ),
        sa.CheckConstraint(
            "created_at >= occurred_at",
            name="ck_engineering_command_events_created_at",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "command_id", "ecid", "instruction_digest"],
            [
                "engineering_commands.company_id",
                "engineering_commands.id",
                "engineering_commands.ecid",
                "engineering_commands.instruction_digest",
            ],
            name="fk_engineering_command_events_command",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_engineering_command_events_actor_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engineering_command_events"),
        sa.UniqueConstraint(
            "command_id",
            "sequence_number",
            name="uq_engineering_command_events_command_sequence",
        ),
    )
    op.create_index(
        "ix_engineering_command_events_command_sequence",
        "engineering_command_events",
        ["company_id", "command_id", "sequence_number", "id"],
    )
    op.create_index(
        "ix_engineering_command_events_company_occurred",
        "engineering_command_events",
        ["company_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_engineering_command_events_company_occurred",
        table_name="engineering_command_events",
    )
    op.drop_index(
        "ix_engineering_command_events_command_sequence",
        table_name="engineering_command_events",
    )
    op.drop_table("engineering_command_events")
    op.drop_index(
        "ix_engineering_commands_approved_queue",
        table_name="engineering_commands",
    )
    op.drop_index(
        "ix_engineering_commands_company_repository",
        table_name="engineering_commands",
    )
    op.drop_index(
        "ix_engineering_commands_company_execution",
        table_name="engineering_commands",
    )
    op.drop_index(
        "ix_engineering_commands_company_approval",
        table_name="engineering_commands",
    )
    op.drop_index(
        "ix_engineering_commands_company_created",
        table_name="engineering_commands",
    )
    op.drop_table("engineering_commands")
    op.drop_table("engineering_command_ecid_sequences")
