"""Add append-only HCP Appointment sequence correction authority.

Revision ID: b5d7f9a1c324
Revises: a4c6e8f0b213
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b5d7f9a1c324"
down_revision: str | Sequence[str] | None = "a4c6e8f0b213"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_hcp_child_repair_scope",
        "hcp_migration_child_repairs",
        ["id", "company_id", "branch_id"],
    )
    op.create_table(
        "hcp_appointment_sequence_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("original_plan_digest", sa.String(64), nullable=False),
        sa.Column("superseded_repair_plan_digest", sa.String(64), nullable=False),
        sa.Column("sequencing_contract_version", sa.String(100), nullable=False),
        sa.Column("sequencing_digest", sa.String(64), nullable=False),
        sa.Column("checkpoint_digest", sa.String(64), nullable=False),
        sa.Column("plan_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "generation >= 1", name="ck_hcp_appointment_sequence_plan_generation"
        ),
        sa.CheckConstraint(
            "status IN ('qualified','applied','superseded')",
            name="ck_hcp_appointment_sequence_plan_status",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_appointment_sequence_plan_master_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["repair_id", "company_id", "branch_id"],
            [
                "hcp_migration_child_repairs.id",
                "hcp_migration_child_repairs.company_id",
                "hcp_migration_child_repairs.branch_id",
            ],
            name="fk_hcp_appointment_sequence_plan_repair_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            name="uq_hcp_appointment_sequence_plan_scope",
        ),
        sa.UniqueConstraint(
            "master_run_id",
            "plan_digest",
            name="uq_hcp_appointment_sequence_plan_digest",
        ),
    )
    op.create_table(
        "hcp_appointment_sequence_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("failed_child_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prior_sequence", sa.Integer(), nullable=False),
        sa.Column("corrected_sequence", sa.Integer(), nullable=False),
        sa.Column("source_identity_digest", sa.String(64), nullable=False),
        sa.Column("correction_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "prior_sequence >= 1", name="ck_hcp_appointment_correction_prior"
        ),
        sa.CheckConstraint(
            "corrected_sequence >= 1", name="ck_hcp_appointment_correction_corrected"
        ),
        sa.CheckConstraint(
            "status IN ('qualified','applied')",
            name="ck_hcp_appointment_correction_status",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_plan_id", "company_id", "branch_id"],
            [
                "hcp_appointment_sequence_plans.id",
                "hcp_appointment_sequence_plans.company_id",
                "hcp_appointment_sequence_plans.branch_id",
            ],
            name="fk_hcp_appointment_correction_plan_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_link_id"], ["job_appointment_links.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_plan_id",
            "appointment_link_id",
            name="uq_hcp_appointment_correction_link",
        ),
        sa.UniqueConstraint(
            "sequence_plan_id",
            "correction_digest",
            name="uq_hcp_appointment_correction_digest",
        ),
    )


def downgrade() -> None:
    op.drop_table("hcp_appointment_sequence_corrections")
    op.drop_table("hcp_appointment_sequence_plans")
    op.drop_constraint(
        "uq_hcp_child_repair_scope", "hcp_migration_child_repairs", type_="unique"
    )
