"""create execution composition foundation

Revision ID: e7a9c1d3f526
Revises: d5f7a9c1e326
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e7a9c1d3f526"
down_revision: str | None = "d5f7a9c1e326"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engineering_execution_compositions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_identifier", sa.String(100), nullable=False),
        sa.Column("required_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("effective_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("approved_code_changes", sa.Boolean(), nullable=False),
        sa.Column("repository_key", sa.String(100), nullable=False),
        sa.Column("expected_branch", sa.String(255), nullable=False),
        sa.Column("expected_head", sa.String(40), nullable=False),
        sa.Column("instruction_digest", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("composition_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            name="fk_execution_compositions_execution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_execution_compositions_worker",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "lease_id"],
            ["engineering_worker_leases.company_id", "engineering_worker_leases.id"],
            name="fk_execution_compositions_lease",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('created','expired','revoked')",
            name="ck_execution_compositions_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_execution_compositions_version"),
        sa.CheckConstraint(
            "length(btrim(provider_identifier)) > 0",
            name="ck_execution_compositions_provider",
        ),
        sa.CheckConstraint(
            "length(composition_digest) = 64",
            name="ck_execution_compositions_digest",
        ),
        sa.CheckConstraint(
            "expected_head ~ '^[0-9a-f]{40}$'",
            name="ck_execution_compositions_expected_head",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_execution_compositions_expiration"
        ),
        sa.UniqueConstraint(
            "company_id",
            "execution_id",
            "lease_id",
            name="uq_execution_compositions_execution_lease",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_execution_compositions_company_id"
        ),
    )
    op.create_index(
        "ix_execution_compositions_company_state",
        "engineering_execution_compositions",
        ["company_id", "state", "created_at", "id"],
    )
    op.create_index(
        "ix_execution_compositions_company_execution",
        "engineering_execution_compositions",
        ["company_id", "execution_id", "created_at", "id"],
    )

    op.create_table(
        "engineering_composition_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("composition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_identifier", sa.String(100), nullable=False),
        sa.Column("instruction_digest", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(128), nullable=False),
        sa.Column("composition_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("integrity_method", sa.String(50), nullable=False),
        sa.Column("integrity_key_reference", sa.String(200)),
        sa.Column("integrity_proof", sa.String(4096)),
        sa.ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            name="fk_composition_receipts_composition",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status = 'accepted'", name="ck_composition_receipts_status"
        ),
        sa.CheckConstraint("version = 1", name="ck_composition_receipts_version"),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_composition_receipts_expiration"
        ),
        sa.CheckConstraint(
            "length(btrim(integrity_method)) > 0",
            name="ck_composition_receipts_integrity_method",
        ),
        sa.UniqueConstraint(
            "company_id",
            "composition_id",
            name="uq_composition_receipts_composition",
        ),
    )
    op.create_index(
        "ix_composition_receipts_company_execution",
        "engineering_composition_receipts",
        ["company_id", "execution_id", "created_at", "id"],
    )

    op.create_table(
        "engineering_provider_execution_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("composition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_identifier", sa.String(100), nullable=False),
        sa.Column("attempt_ordinal", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("failure_classification", sa.String(100)),
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True)),
        sa.Column("cancellation_acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            name="fk_provider_attempts_composition",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('prepared','starting','running','completed','failed',"
            "'cancelled','timed_out','quarantined')",
            name="ck_provider_attempts_state",
        ),
        sa.CheckConstraint("attempt_ordinal >= 1", name="ck_provider_attempts_ordinal"),
        sa.CheckConstraint("version >= 1", name="ck_provider_attempts_version"),
        sa.UniqueConstraint(
            "company_id",
            "composition_id",
            "attempt_ordinal",
            name="uq_provider_attempts_composition_ordinal",
        ),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_provider_attempts_idempotency",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_provider_attempts_company_id"),
    )
    op.create_index(
        "ix_provider_attempts_company_state",
        "engineering_provider_execution_attempts",
        ["company_id", "state", "prepared_at", "id"],
    )

    op.create_table(
        "engineering_provider_progress_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("message_code", sa.String(100), nullable=False),
        sa.Column("summary", sa.String(500)),
        sa.Column("percentage", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "attempt_id"],
            [
                "engineering_provider_execution_attempts.company_id",
                "engineering_provider_execution_attempts.id",
            ],
            name="fk_provider_progress_attempt",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "phase IN ('preparing','starting','executing','validating','finalizing')",
            name="ck_provider_progress_phase",
        ),
        sa.CheckConstraint(
            "sequence_number >= 1", name="ck_provider_progress_sequence"
        ),
        sa.CheckConstraint(
            "percentage IS NULL OR percentage BETWEEN 0 AND 100",
            name="ck_provider_progress_percentage",
        ),
        sa.CheckConstraint(
            "length(btrim(message_code)) BETWEEN 1 AND 100",
            name="ck_provider_progress_message_code",
        ),
        sa.CheckConstraint(
            "summary IS NULL OR length(summary) <= 500",
            name="ck_provider_progress_summary",
        ),
        sa.UniqueConstraint(
            "company_id",
            "attempt_id",
            "sequence_number",
            name="uq_provider_progress_attempt_sequence",
        ),
    )
    op.create_index(
        "ix_provider_progress_company_attempt",
        "engineering_provider_progress_events",
        ["company_id", "attempt_id", "sequence_number"],
    )

    op.create_table(
        "engineering_normalized_provider_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("composition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence_summary", postgresql.JSONB(), nullable=False),
        sa.Column("validation_summary", postgresql.JSONB(), nullable=False),
        sa.Column("output_references", postgresql.JSONB(), nullable=False),
        sa.Column("failure_classification", sa.String(100)),
        sa.Column(
            "repository_mutated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=False),
        sa.Column("disposition_reason", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "attempt_id"],
            [
                "engineering_provider_execution_attempts.company_id",
                "engineering_provider_execution_attempts.id",
            ],
            name="fk_normalized_results_attempt",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "composition_id"],
            [
                "engineering_execution_compositions.company_id",
                "engineering_execution_compositions.id",
            ],
            name="fk_normalized_results_composition",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('succeeded','failed','cancelled')",
            name="ck_normalized_results_status",
        ),
        sa.CheckConstraint(
            "disposition IN ('accepted','rejected','quarantined')",
            name="ck_normalized_results_disposition",
        ),
        sa.CheckConstraint(
            "repository_mutated = false",
            name="ck_normalized_results_repository_not_mutated",
        ),
        sa.CheckConstraint(
            "disposition = 'accepted' OR length(btrim(disposition_reason)) > 0",
            name="ck_normalized_results_reason",
        ),
        sa.UniqueConstraint(
            "company_id", "attempt_id", name="uq_normalized_results_attempt"
        ),
    )
    op.create_index(
        "ix_normalized_results_company_disposition",
        "engineering_normalized_provider_results",
        ["company_id", "disposition", "received_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_normalized_results_company_disposition",
        table_name="engineering_normalized_provider_results",
    )
    op.drop_table("engineering_normalized_provider_results")
    op.drop_index(
        "ix_provider_progress_company_attempt",
        table_name="engineering_provider_progress_events",
    )
    op.drop_table("engineering_provider_progress_events")
    op.drop_index(
        "ix_provider_attempts_company_state",
        table_name="engineering_provider_execution_attempts",
    )
    op.drop_table("engineering_provider_execution_attempts")
    op.drop_index(
        "ix_composition_receipts_company_execution",
        table_name="engineering_composition_receipts",
    )
    op.drop_table("engineering_composition_receipts")
    op.drop_index(
        "ix_execution_compositions_company_execution",
        table_name="engineering_execution_compositions",
    )
    op.drop_index(
        "ix_execution_compositions_company_state",
        table_name="engineering_execution_compositions",
    )
    op.drop_table("engineering_execution_compositions")
