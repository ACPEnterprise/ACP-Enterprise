"""Bind HCP repair and Appointment correction evidence scope.

Revision ID: j4h3i82e9c5a
Revises: i3g2h71d8b4z
"""

from collections.abc import Sequence

from alembic import op

revision: str = "j4h3i82e9c5a"
down_revision: str | Sequence[str] | None = "i3g2h71d8b4z"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_job_appointment_link_correction_scope",
        "job_appointment_links",
        ["id", "company_id", "branch_id", "job_id", "appointment_id"],
    )

    replacements = (
        (
            "hcp_migration_child_repairs_repair_child_run_id_fkey",
            "fk_hcp_child_repair_child_scope",
            "operational_migration_runs",
            "repair_child_run_id",
        ),
        (
            "fk_hcp_child_repair_failed_child",
            "fk_hcp_child_repair_failed_scope",
            "operational_migration_runs",
            "failed_child_run_id",
        ),
        (
            "fk_hcp_child_repair_parent",
            "fk_hcp_child_repair_parent_scope",
            "hcp_migration_child_repairs",
            "parent_repair_id",
        ),
        (
            "fk_hcp_child_repair_sequence_plan",
            "fk_hcp_child_repair_sequence_plan_scope",
            "hcp_appointment_sequence_plans",
            "sequence_plan_id",
        ),
    )
    for old_name, new_name, parent, child_col in replacements:
        op.drop_constraint(
            old_name, "hcp_migration_child_repairs", type_="foreignkey"
        )
        op.create_foreign_key(
            new_name,
            "hcp_migration_child_repairs",
            parent,
            [child_col, "company_id", "branch_id"],
            ["id", "company_id", "branch_id"],
            ondelete="RESTRICT",
        )

    op.drop_constraint(
        "hcp_appointment_sequence_corrections_appointment_link_id_fkey",
        "hcp_appointment_sequence_corrections",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_hcp_appointment_correction_link_scope",
        "hcp_appointment_sequence_corrections",
        "job_appointment_links",
        [
            "appointment_link_id",
            "company_id",
            "branch_id",
            "job_id",
            "appointment_id",
        ],
        ["id", "company_id", "branch_id", "job_id", "appointment_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hcp_appointment_correction_failed_run_scope",
        "hcp_appointment_sequence_corrections",
        "operational_migration_runs",
        ["failed_child_run_id", "company_id", "branch_id"],
        ["id", "company_id", "branch_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_hcp_appointment_correction_failed_run_scope",
        "hcp_appointment_sequence_corrections",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_hcp_appointment_correction_link_scope",
        "hcp_appointment_sequence_corrections",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "hcp_appointment_sequence_corrections_appointment_link_id_fkey",
        "hcp_appointment_sequence_corrections",
        "job_appointment_links",
        ["appointment_link_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    replacements = (
        (
            "fk_hcp_child_repair_sequence_plan_scope",
            "fk_hcp_child_repair_sequence_plan",
            "hcp_appointment_sequence_plans",
            "sequence_plan_id",
        ),
        (
            "fk_hcp_child_repair_parent_scope",
            "fk_hcp_child_repair_parent",
            "hcp_migration_child_repairs",
            "parent_repair_id",
        ),
        (
            "fk_hcp_child_repair_failed_scope",
            "fk_hcp_child_repair_failed_child",
            "operational_migration_runs",
            "failed_child_run_id",
        ),
        (
            "fk_hcp_child_repair_child_scope",
            "hcp_migration_child_repairs_repair_child_run_id_fkey",
            "operational_migration_runs",
            "repair_child_run_id",
        ),
    )
    for scoped_name, old_name, parent, child_col in replacements:
        op.drop_constraint(
            scoped_name, "hcp_migration_child_repairs", type_="foreignkey"
        )
        op.create_foreign_key(
            old_name,
            "hcp_migration_child_repairs",
            parent,
            [child_col],
            ["id"],
            ondelete="RESTRICT",
        )

    op.drop_constraint(
        "uq_job_appointment_link_correction_scope",
        "job_appointment_links",
        type_="unique",
    )
