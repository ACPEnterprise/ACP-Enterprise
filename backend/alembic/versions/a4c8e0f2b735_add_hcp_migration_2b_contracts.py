"""Add HCP migration 2B persistence admission contracts.

Revision ID: a4c8e0f2b735
Revises: f3b7d9e1a624
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4c8e0f2b735"
down_revision: str | Sequence[str] | None = "f3b7d9e1a624"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "hcp_migration_master_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("package_digest", sa.String(64), nullable=False),
        sa.Column("collection_digests", JSON, nullable=False),
        sa.Column("transformation_contracts", JSON, nullable=False),
        sa.Column("owner_receipts", JSON, nullable=False),
        sa.Column("schema_head", sa.String(32), nullable=False),
        sa.Column("implementation_version", sa.String(100), nullable=False),
        sa.Column("supported_entities", JSON, nullable=False),
        sa.Column("baseline_counts", JSON, nullable=False),
        sa.Column("source_counts", JSON, nullable=False),
        sa.Column("transformed_counts", JSON, nullable=False),
        sa.Column("persisted_counts", JSON, nullable=False),
        sa.Column("hold_counts", JSON, nullable=False),
        sa.Column("exception_counts", JSON, nullable=False),
        sa.Column("rejection_counts", JSON, nullable=False),
        sa.Column("unresolved_counts", JSON, nullable=False),
        sa.Column("reconciliation_digest", sa.String(64), nullable=True),
        sa.Column("replay_state", JSON, nullable=False),
        sa.Column("resume_state", JSON, nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("attestation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('prepared','running','interrupted','completed','failed')",
            name="ck_hcp_master_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_hcp_master_run_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "branch_id", "input_digest", name="uq_hcp_master_input"
        ),
    )
    op.create_table(
        "hcp_customer_source_lineage",
        sa.Column("id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("master_run_id", UUID, nullable=False),
        sa.Column("customer_source_identity_id", UUID, nullable=True),
        sa.Column("native_customer_id", sa.String(191), nullable=False),
        sa.Column("package_digest", sa.String(64), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("transformation_contract", sa.String(100), nullable=False),
        sa.Column("transformation_digest", sa.String(64), nullable=False),
        sa.Column("owner_disposition", sa.String(100), nullable=True),
        sa.Column("source_timestamps", JSON, nullable=False),
        sa.Column("source_context", JSON, nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"], ["branches.company_id", "branches.id"],
            name="fk_hcp_customer_lineage_branch_scope", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["master_run_id"], ["hcp_migration_master_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_source_identity_id"], ["customer_source_identities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "native_customer_id", name="uq_hcp_customer_lineage_native"),
        sa.UniqueConstraint("company_id", "evidence_digest", name="uq_hcp_customer_lineage_replay"),
    )
    op.create_table(
        "hcp_employee_source_crosswalks",
        sa.Column("id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("master_run_id", UUID, nullable=False),
        sa.Column("prior_evidence_id", UUID, nullable=True),
        sa.Column("employee_id", UUID, nullable=True),
        sa.Column("native_employee_id", sa.String(191), nullable=False),
        sa.Column("disposition", sa.String(100), nullable=False),
        sa.Column("package_digest", sa.String(64), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("owner_receipt_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("evidence_version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("disposition IN ('CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE','EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS')", name="ck_hcp_employee_crosswalk_disposition"),
        sa.CheckConstraint("disposition <> 'EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS' OR employee_id IS NULL", name="ck_hcp_employee_crosswalk_excluded_no_target"),
        sa.ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], name="fk_hcp_employee_crosswalk_branch_scope", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["master_run_id"], ["hcp_migration_master_runs.id"]),
        sa.ForeignKeyConstraint(["prior_evidence_id"], ["hcp_employee_source_crosswalks.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "native_employee_id", "evidence_version", name="uq_hcp_employee_crosswalk_version"),
        sa.UniqueConstraint("company_id", "evidence_digest", name="uq_hcp_employee_crosswalk_replay"),
    )
    op.create_index("uq_hcp_employee_crosswalk_target", "hcp_employee_source_crosswalks", ["company_id", "employee_id"], unique=True, postgresql_where=sa.text("employee_id IS NOT NULL"))
    op.create_table(
        "hcp_migration_holds",
        sa.Column("id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("master_run_id", UUID, nullable=False),
        sa.Column("prior_hold_id", UUID, nullable=True),
        sa.Column("entity_kind", sa.String(40), nullable=False),
        sa.Column("native_id", sa.String(191), nullable=False),
        sa.Column("hold_code", sa.String(100), nullable=False),
        sa.Column("owner_disposition", sa.String(100), nullable=True),
        sa.Column("package_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("reconciliation_key", sa.String(191), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("hold_digest", sa.String(64), nullable=False),
        sa.Column("evidence_version", sa.Integer(), nullable=False),
        sa.Column("operational_effects_enabled", sa.Boolean(), nullable=False),
        sa.Column("financial_truth_accepted", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('HELD','RELEASED')", name="ck_hcp_hold_state"),
        sa.CheckConstraint("operational_effects_enabled = false AND financial_truth_accepted = false", name="ck_hcp_hold_no_effects"),
        sa.ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], name="fk_hcp_hold_branch_scope", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["master_run_id"], ["hcp_migration_master_runs.id"]),
        sa.ForeignKeyConstraint(["prior_hold_id"], ["hcp_migration_holds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "master_run_id", "entity_kind", "native_id", name="uq_hcp_hold_native_run"),
        sa.UniqueConstraint("company_id", "hold_digest", name="uq_hcp_hold_replay"),
    )
    op.execute(
        """
        CREATE FUNCTION reject_hcp_migration_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'HCP migration evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "hcp_customer_source_lineage",
        "hcp_employee_source_crosswalks",
        "hcp_migration_holds",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_hcp_migration_evidence_mutation()
            """
        )


def downgrade() -> None:
    for table in (
        "hcp_migration_holds",
        "hcp_employee_source_crosswalks",
        "hcp_customer_source_lineage",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_table("hcp_migration_holds")
    op.drop_index("uq_hcp_employee_crosswalk_target", table_name="hcp_employee_source_crosswalks")
    op.drop_table("hcp_employee_source_crosswalks")
    op.drop_table("hcp_customer_source_lineage")
    op.drop_table("hcp_migration_master_runs")
    op.execute("DROP FUNCTION IF EXISTS reject_hcp_migration_evidence_mutation()")
