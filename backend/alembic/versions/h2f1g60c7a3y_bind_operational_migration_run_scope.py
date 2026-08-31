"""Bind operational Migration evidence to exact tenant run scope.

Revision ID: h2f1g60c7a3y
Revises: g1e0f59b6z2x
"""

from collections.abc import Sequence

from alembic import op

revision: str = "h2f1g60c7a3y"
down_revision: str | Sequence[str] | None = "g1e0f59b6z2x"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BRANCH_CHILDREN = (
    (
        "operational_migration_job_source_identities",
        "operational_migration_job_source_identities_first_run_id_fkey",
        "fk_job_source_identity_first_run_scope",
        "first_run_id",
    ),
    (
        "operational_migration_appointment_source_identities",
        "operational_migration_appointment_source_iden_first_run_id_fkey",
        "fk_appointment_source_identity_first_run_scope",
        "first_run_id",
    ),
    (
        "operational_migration_estimate_source_identities",
        "operational_migration_estimate_source_identit_first_run_id_fkey",
        "fk_estimate_source_identity_first_run_scope",
        "first_run_id",
    ),
    (
        "operational_migration_invoice_source_identities",
        "operational_migration_invoice_source_identiti_first_run_id_fkey",
        "fk_invoice_source_identity_first_run_scope",
        "first_run_id",
    ),
    (
        "operational_migration_payment_source_identities",
        "operational_migration_payment_source_identiti_first_run_id_fkey",
        "fk_payment_source_identity_first_run_scope",
        "first_run_id",
    ),
    (
        "operational_migration_artifacts",
        "operational_migration_artifacts_first_run_id_fkey",
        "fk_migration_artifact_first_run_scope",
        "first_run_id",
    ),
    (
        "operational_migration_history_entries",
        "operational_migration_history_entries_first_run_id_fkey",
        "fk_migration_history_first_run_scope",
        "first_run_id",
    ),
    (
        "operational_migration_phase_completions",
        "operational_migration_phase_completions_supporting_run_id_fkey",
        "fk_migration_phase_supporting_run_scope",
        "supporting_run_id",
    ),
)

COMPANY_CHILDREN = (
    (
        "operational_migration_estimate_line_item_source_identities",
        "operational_migration_estimate_line_item_sour_first_run_id_fkey",
        "fk_estimate_item_source_first_run_scope",
    ),
    (
        "operational_migration_invoice_line_item_source_identities",
        "operational_migration_invoice_line_item_sourc_first_run_id_fkey",
        "fk_invoice_item_source_first_run_scope",
    ),
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_operational_run_company",
        "operational_migration_runs",
        ["id", "company_id"],
    )
    op.drop_constraint(
        "operational_migration_runs_branch_id_fkey",
        "operational_migration_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_operational_run_branch_scope",
        "operational_migration_runs",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "fk_operational_repair_original",
        "operational_migration_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_operational_repair_original_scope",
        "operational_migration_runs",
        "operational_migration_runs",
        ["repair_of_run_id", "company_id", "branch_id"],
        ["id", "company_id", "branch_id"],
        ondelete="RESTRICT",
    )
    for table, old_name, new_name, run_column in BRANCH_CHILDREN:
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name,
            table,
            "operational_migration_runs",
            [run_column, "company_id", "branch_id"],
            ["id", "company_id", "branch_id"],
            ondelete="RESTRICT",
        )
    for table, old_name, new_name in COMPANY_CHILDREN:
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name,
            table,
            "operational_migration_runs",
            ["first_run_id", "company_id"],
            ["id", "company_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for table, old_name, new_name in reversed(COMPANY_CHILDREN):
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(
            old_name,
            table,
            "operational_migration_runs",
            ["first_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    for table, old_name, new_name, run_column in reversed(BRANCH_CHILDREN):
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(
            old_name,
            table,
            "operational_migration_runs",
            [run_column],
            ["id"],
            ondelete="RESTRICT",
        )
    op.drop_constraint(
        "fk_operational_repair_original_scope",
        "operational_migration_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_operational_repair_original",
        "operational_migration_runs",
        "operational_migration_runs",
        ["repair_of_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "fk_operational_run_branch_scope",
        "operational_migration_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "operational_migration_runs_branch_id_fkey",
        "operational_migration_runs",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_operational_run_company",
        "operational_migration_runs",
        type_="unique",
    )
