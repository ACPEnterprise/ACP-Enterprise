"""Add provider-neutral operational artifact and cutover foundation.

Revision ID: c4f0a6b8e152
Revises: b3e9f5a7d041
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4f0a6b8e152"
down_revision: str | Sequence[str] | None = "b3e9f5a7d041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENTS = "('customer','service_location','job','appointment','estimate','invoice')"


def upgrade() -> None:
    op.alter_column(
        "operational_migration_runs",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(40),
        existing_nullable=False,
    )
    op.drop_constraint(
        "ck_operational_migration_runs_status",
        "operational_migration_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_migration_runs_status",
        "operational_migration_runs",
        "status IN ('running','interrupted','completed',"
        "'completed_with_exceptions','failed')",
    )
    op.create_table(
        "operational_migration_cutover_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "evaluated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("projected_status", sa.String(40), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("blocker_codes", postgresql.JSONB(), nullable=False),
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "projected_status IN ('ready_for_owner_review','not_ready')",
            name="ck_migration_cutover_assessment_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_cutover_assessment_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_migration_cutover_assessment_latest",
        "operational_migration_cutover_assessments",
        ["company_id", "branch_id", "evaluated_at"],
    )
    op.create_table(
        "operational_migration_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_id_sha256", sa.String(64), nullable=False),
        sa.Column("parent_type", sa.String(30), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_category", sa.String(20), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("media_type", sa.String(127), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("source_checksum", sa.String(128), nullable=True),
        sa.Column("acp_checksum", sa.String(128), nullable=True),
        sa.Column("retrieval_state", sa.String(20), nullable=False),
        sa.Column("transfer_state", sa.String(20), nullable=False),
        sa.Column("validation_state", sa.String(20), nullable=False),
        sa.Column("failure_classification", sa.String(80), nullable=True),
        sa.Column("retry_eligible", sa.Boolean(), nullable=False),
        sa.Column("required_for_cutover", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "artifact_category IN ('attachment','document','photo','other')",
            name="ck_migration_artifacts_category",
        ),
        sa.CheckConstraint(
            f"parent_type IN {PARENTS}",
            name="ck_migration_artifacts_parent_type",
        ),
        sa.CheckConstraint(
            "retrieval_state IN ('pending','available','unavailable')",
            name="ck_migration_artifacts_retrieval",
        ),
        sa.CheckConstraint(
            "transfer_state IN ('pending','transferred','failed','not_required')",
            name="ck_migration_artifacts_transfer",
        ),
        sa.CheckConstraint(
            "validation_state IN ('pending','valid','invalid','not_validated')",
            name="ck_migration_artifacts_validation",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_migration_artifacts_attempts"
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0",
            name="ck_migration_artifacts_size",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_artifacts_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_id_sha256",
            name="uq_migration_artifacts_source_identity",
        ),
    )
    op.create_index(
        "ix_migration_artifacts_parent",
        "operational_migration_artifacts",
        ["company_id", "parent_type", "parent_id"],
    )
    op.create_index(
        "ix_migration_artifacts_readiness",
        "operational_migration_artifacts",
        [
            "company_id",
            "branch_id",
            "required_for_cutover",
            "transfer_state",
            "validation_state",
        ],
    )
    op.create_table(
        "operational_migration_audit_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_descriptor_sha256", sa.String(64), nullable=False),
        sa.Column("completion_status", sa.String(40), nullable=False),
        sa.Column("entity_counts", postgresql.JSONB(), nullable=False),
        sa.Column("artifact_outcomes", postgresql.JSONB(), nullable=False),
        sa.Column("reconciliation_differences", postgresql.JSONB(), nullable=False),
        sa.Column("unresolved_categories", postgresql.JSONB(), nullable=False),
        sa.Column("run_ids", postgresql.JSONB(), nullable=False),
        sa.Column("period_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "completion_status IN ('completed','completed_with_exceptions','incomplete')",
            name="ck_migration_audit_summary_status",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["operational_migration_cutover_assessments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_audit_summary_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "operational_migration_phase_completions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phase_code", sa.String(40), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("dry_run_completed", sa.Boolean(), nullable=False),
        sa.Column("import_completed", sa.Boolean(), nullable=False),
        sa.Column("idempotent_rerun_validated", sa.Boolean(), nullable=False),
        sa.Column("supporting_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_phase_completion_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supporting_run_id"],
            ["operational_migration_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "phase_code",
            name="uq_migration_phase_completion",
        ),
    )
    op.create_table(
        "operational_migration_record_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("source_id_sha256", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=True),
        sa.Column("retry_eligible", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("parent_linked", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('accepted','rejected','duplicate','unresolved','skipped')",
            name="ck_migration_record_outcomes_disposition",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "entity_type",
            "source_id_sha256",
            name="uq_migration_record_outcomes_identity",
        ),
    )
    op.create_index(
        "ix_migration_record_outcomes_run_disposition",
        "operational_migration_record_outcomes",
        ["run_id", "disposition", "entity_type"],
    )
    op.create_table(
        "operational_migration_artifact_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("failure_classification", sa.String(80), nullable=True),
        sa.Column("retry_eligible", sa.Boolean(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["operational_migration_artifacts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id",
            "attempt_number",
            name="uq_migration_artifact_attempt_number",
        ),
    )
    op.create_table(
        "operational_migration_history_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_id_sha256", sa.String(64), nullable=False),
        sa.Column("parent_type", sa.String(30), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("employee_source_ref_sha256", sa.String(64), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attribution_status", sa.String(20), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("activity_category", sa.String(64), nullable=False),
        sa.Column("supported_tags", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_attributes", postgresql.JSONB(), nullable=False),
        sa.Column("unsupported_attribute_keys", postgresql.JSONB(), nullable=False),
        sa.Column("external_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attribution_status IN ('resolved','unresolved','not_provided')",
            name="ck_migration_history_attribution",
        ),
        sa.CheckConstraint(
            "entry_type IN ('note','activity')",
            name="ck_migration_history_entry_type",
        ),
        sa.CheckConstraint(
            f"parent_type IN {PARENTS}",
            name="ck_migration_history_parent_type",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_migration_history_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_migration_history_employee_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_id_sha256",
            name="uq_migration_history_source_identity",
        ),
    )
    op.create_index(
        "ix_migration_history_parent",
        "operational_migration_history_entries",
        ["company_id", "parent_type", "parent_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_migration_history_parent",
        table_name="operational_migration_history_entries",
    )
    op.drop_table("operational_migration_history_entries")
    op.drop_table("operational_migration_artifact_attempts")
    op.drop_index(
        "ix_migration_record_outcomes_run_disposition",
        table_name="operational_migration_record_outcomes",
    )
    op.drop_table("operational_migration_record_outcomes")
    op.drop_table("operational_migration_phase_completions")
    op.drop_table("operational_migration_audit_summaries")
    op.drop_index(
        "ix_migration_artifacts_readiness",
        table_name="operational_migration_artifacts",
    )
    op.drop_index(
        "ix_migration_artifacts_parent",
        table_name="operational_migration_artifacts",
    )
    op.drop_table("operational_migration_artifacts")
    op.drop_index(
        "ix_migration_cutover_assessment_latest",
        table_name="operational_migration_cutover_assessments",
    )
    op.drop_table("operational_migration_cutover_assessments")
    op.drop_constraint(
        "ck_operational_migration_runs_status",
        "operational_migration_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_migration_runs_status",
        "operational_migration_runs",
        "status IN ('running','completed','failed')",
    )
    op.alter_column(
        "operational_migration_runs",
        "status",
        existing_type=sa.String(40),
        type_=sa.String(20),
        existing_nullable=False,
    )
