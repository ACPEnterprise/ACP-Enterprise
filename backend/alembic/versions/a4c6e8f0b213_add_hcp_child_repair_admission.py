"""Add HCP child conformance admission and repair lineage.

Revision ID: a4c6e8f0b213
Revises: f3a5c7e9b102
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a4c6e8f0b213"
down_revision: str | Sequence[str] | None = "f3a5c7e9b102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_operational_master_domain", "operational_migration_runs", type_="unique"
    )
    op.add_column(
        "operational_migration_runs",
        sa.Column("repair_of_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "operational_migration_runs",
        sa.Column(
            "repair_generation", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.create_foreign_key(
        "fk_operational_repair_original",
        "operational_migration_runs",
        "operational_migration_runs",
        ["repair_of_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_operational_master_domain_generation",
        "operational_migration_runs",
        ["master_run_id", "master_domain", "repair_generation"],
    )
    op.create_unique_constraint(
        "uq_operational_run_scope",
        "operational_migration_runs",
        ["id", "company_id", "branch_id"],
    )

    op.create_table(
        "hcp_migration_child_admissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(20), nullable=False),
        sa.Column("execution_status", sa.String(40), nullable=False),
        sa.Column("conformance", sa.String(30), nullable=False),
        sa.Column("plan_digest", sa.String(64), nullable=False),
        sa.Column("expected_counts", postgresql.JSONB(), nullable=False),
        sa.Column("actual_counts", postgresql.JSONB(), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("admission_digest", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "domain IN ('customer','operational','financial','history')",
            name="ck_hcp_child_admission_domain",
        ),
        sa.CheckConstraint(
            "conformance IN ('PLAN_CONFORMING','PLAN_NONCONFORMING')",
            name="ck_hcp_child_admission_conformance",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_child_admission_master_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "master_run_id", "domain", "child_run_id", name="uq_hcp_child_admission"
        ),
        sa.UniqueConstraint(
            "master_run_id",
            "domain",
            "admission_digest",
            name="uq_hcp_child_admission_replay",
        ),
    )
    op.create_index(
        "uq_hcp_child_admission_conforming_domain",
        "hcp_migration_child_admissions",
        ["master_run_id", "domain"],
        unique=True,
        postgresql_where=sa.text("conformance = 'PLAN_CONFORMING'"),
    )
    op.create_table(
        "hcp_migration_child_repairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "original_child_run_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("repair_child_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("domain", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("original_plan_digest", sa.String(64), nullable=False),
        sa.Column("repair_plan_digest", sa.String(64), nullable=False),
        sa.Column("immutable_input_digest", sa.String(64), nullable=False),
        sa.Column("repair_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "domain IN ('operational','financial','history')",
            name="ck_hcp_child_repair_domain",
        ),
        sa.CheckConstraint(
            "status IN ('qualified','running','completed','failed')",
            name="ck_hcp_child_repair_status",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_child_repair_master_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["original_child_run_id", "company_id", "branch_id"],
            [
                "operational_migration_runs.id",
                "operational_migration_runs.company_id",
                "operational_migration_runs.branch_id",
            ],
            name="fk_hcp_child_repair_original_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["repair_child_run_id"],
            ["operational_migration_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "master_run_id",
            "domain",
            "repair_digest",
            name="uq_hcp_child_repair_replay",
        ),
    )


def downgrade() -> None:
    op.drop_table("hcp_migration_child_repairs")
    op.drop_table("hcp_migration_child_admissions")
    op.drop_constraint(
        "uq_operational_run_scope", "operational_migration_runs", type_="unique"
    )
    op.drop_constraint(
        "uq_operational_master_domain_generation",
        "operational_migration_runs",
        type_="unique",
    )
    op.drop_constraint(
        "fk_operational_repair_original",
        "operational_migration_runs",
        type_="foreignkey",
    )
    op.drop_column("operational_migration_runs", "repair_generation")
    op.drop_column("operational_migration_runs", "repair_of_run_id")
    op.create_unique_constraint(
        "uq_operational_master_domain",
        "operational_migration_runs",
        ["master_run_id", "master_domain"],
    )
