"""Add immutable cutover plan and rehearsal evidence.

Revision ID: e0a6c2d8f351
Revises: d9f5b1c7e240
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e0a6c2d8f351"
down_revision: str | Sequence[str] | None = "d9f5b1c7e240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_customer_cutover_readiness_scope",
        "customer_migration_cutover_readiness_evidence",
        ["id", "company_id", "branch_id"],
    )
    op.create_table(
        "customer_migration_cutover_plan_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "readiness_evidence_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("planned_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_key", sa.String(64), nullable=False),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("plan_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("ordered_steps", postgresql.JSONB(), nullable=False),
        sa.Column("dependency_graph", postgresql.JSONB(), nullable=False),
        sa.Column("preconditions", postgresql.JSONB(), nullable=False),
        sa.Column("rollback_prerequisites", postgresql.JSONB(), nullable=False),
        sa.Column("owner_checkpoints", postgresql.JSONB(), nullable=False),
        sa.Column("blocking_conditions", postgresql.JSONB(), nullable=False),
        sa.Column("required_approvals", postgresql.JSONB(), nullable=False),
        sa.Column("recovery_instructions", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready_for_owner_approval','blocked')",
            name="ck_customer_cutover_plan_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_cutover_plan_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["readiness_evidence_id", "company_id", "branch_id"],
            [
                "customer_migration_cutover_readiness_evidence.id",
                "customer_migration_cutover_readiness_evidence.company_id",
                "customer_migration_cutover_readiness_evidence.branch_id",
            ],
            name="fk_customer_cutover_plan_readiness_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["planned_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "company_id", "branch_id", name="uq_customer_cutover_plan_scope"
        ),
        sa.UniqueConstraint(
            "company_id", "branch_id", "plan_key", name="uq_customer_cutover_plan_key"
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "evidence_digest",
            name="uq_customer_cutover_plan_replay",
        ),
    )
    op.create_index(
        "ix_customer_cutover_plan_latest",
        "customer_migration_cutover_plan_evidence",
        ["company_id", "branch_id", "created_at"],
    )
    op.create_table(
        "customer_migration_cutover_rehearsal_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('simulated_success','blocked','interrupted')",
            name="ck_customer_cutover_rehearsal_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_cutover_rehearsal_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "company_id", "branch_id"],
            [
                "customer_migration_cutover_plan_evidence.id",
                "customer_migration_cutover_plan_evidence.company_id",
                "customer_migration_cutover_plan_evidence.branch_id",
            ],
            name="fk_customer_cutover_rehearsal_plan_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "company_id", "branch_id", name="uq_customer_cutover_rehearsal_scope"
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "plan_id",
            "evidence_digest",
            name="uq_customer_cutover_rehearsal_replay",
        ),
    )
    op.create_table(
        "customer_migration_cutover_rehearsal_step_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rehearsal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_code", sa.String(100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("recovery_instruction_code", sa.String(100), nullable=True),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "ordinal >= 0", name="ck_customer_cutover_rehearsal_step_ordinal"
        ),
        sa.CheckConstraint(
            "outcome IN ('eligible','simulated_success','blocked','skipped')",
            name="ck_customer_cutover_rehearsal_step_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["rehearsal_id", "company_id", "branch_id"],
            [
                "customer_migration_cutover_rehearsal_evidence.id",
                "customer_migration_cutover_rehearsal_evidence.company_id",
                "customer_migration_cutover_rehearsal_evidence.branch_id",
            ],
            name="fk_customer_cutover_rehearsal_step_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rehearsal_id", "ordinal", name="uq_customer_cutover_rehearsal_step_order"
        ),
        sa.UniqueConstraint(
            "rehearsal_id",
            "step_id",
            name="uq_customer_cutover_rehearsal_step_identity",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_cutover_evidence_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'cutover planning evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "customer_migration_cutover_plan_evidence",
        "customer_migration_cutover_rehearsal_evidence",
        "customer_migration_cutover_rehearsal_step_evidence",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table_name}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_cutover_evidence_mutation()"
        )


def downgrade() -> None:
    for table_name in (
        "customer_migration_cutover_plan_evidence",
        "customer_migration_cutover_rehearsal_evidence",
        "customer_migration_cutover_rehearsal_step_evidence",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS reject_cutover_evidence_mutation()")
    op.drop_table("customer_migration_cutover_rehearsal_step_evidence")
    op.drop_table("customer_migration_cutover_rehearsal_evidence")
    op.drop_index(
        "ix_customer_cutover_plan_latest",
        table_name="customer_migration_cutover_plan_evidence",
    )
    op.drop_table("customer_migration_cutover_plan_evidence")
    op.drop_constraint(
        "uq_customer_cutover_readiness_scope",
        "customer_migration_cutover_readiness_evidence",
        type_="unique",
    )
