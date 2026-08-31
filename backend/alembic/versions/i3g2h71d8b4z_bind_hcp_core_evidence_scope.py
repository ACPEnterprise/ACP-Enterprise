"""Bind core HCP evidence to tenant and master authority.

Revision ID: i3g2h71d8b4z
Revises: h2f1g60c7a3y
"""

from collections.abc import Sequence

from alembic import op

revision: str = "i3g2h71d8b4z"
down_revision: str | Sequence[str] | None = "h2f1g60c7a3y"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_hcp_employee_crosswalk_company",
        "hcp_employee_source_crosswalks",
        ["id", "company_id"],
    )
    op.create_unique_constraint(
        "uq_hcp_hold_company",
        "hcp_migration_holds",
        ["id", "company_id"],
    )

    replacements = (
        (
            "hcp_customer_source_lineage",
            "hcp_customer_source_lineage_master_run_id_fkey",
            "fk_hcp_customer_lineage_master_scope",
            "hcp_migration_master_runs",
            ["master_run_id", "company_id", "branch_id"],
            ["id", "company_id", "branch_id"],
        ),
        (
            "hcp_customer_source_lineage",
            "hcp_customer_source_lineage_customer_source_identity_id_fkey",
            "fk_hcp_customer_lineage_source_scope",
            "customer_source_identities",
            ["customer_source_identity_id", "company_id"],
            ["id", "company_id"],
        ),
        (
            "hcp_employee_source_crosswalks",
            "hcp_employee_source_crosswalks_master_run_id_fkey",
            "fk_hcp_employee_crosswalk_master_scope",
            "hcp_migration_master_runs",
            ["master_run_id", "company_id", "branch_id"],
            ["id", "company_id", "branch_id"],
        ),
        (
            "hcp_employee_source_crosswalks",
            "hcp_employee_source_crosswalks_employee_id_fkey",
            "fk_hcp_employee_crosswalk_target_scope",
            "employees",
            ["employee_id", "company_id"],
            ["id", "company_id"],
        ),
        (
            "hcp_employee_source_crosswalks",
            "hcp_employee_source_crosswalks_prior_evidence_id_fkey",
            "fk_hcp_employee_crosswalk_prior_scope",
            "hcp_employee_source_crosswalks",
            ["prior_evidence_id", "company_id"],
            ["id", "company_id"],
        ),
        (
            "hcp_migration_holds",
            "hcp_migration_holds_master_run_id_fkey",
            "fk_hcp_hold_master_scope",
            "hcp_migration_master_runs",
            ["master_run_id", "company_id", "branch_id"],
            ["id", "company_id", "branch_id"],
        ),
        (
            "hcp_migration_holds",
            "hcp_migration_holds_prior_hold_id_fkey",
            "fk_hcp_hold_prior_scope",
            "hcp_migration_holds",
            ["prior_hold_id", "company_id"],
            ["id", "company_id"],
        ),
    )
    for table, old_name, new_name, parent, child_cols, parent_cols in replacements:
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name,
            table,
            parent,
            child_cols,
            parent_cols,
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    replacements = (
        (
            "hcp_migration_holds",
            "fk_hcp_hold_prior_scope",
            "hcp_migration_holds_prior_hold_id_fkey",
            "hcp_migration_holds",
            "prior_hold_id",
        ),
        (
            "hcp_migration_holds",
            "fk_hcp_hold_master_scope",
            "hcp_migration_holds_master_run_id_fkey",
            "hcp_migration_master_runs",
            "master_run_id",
        ),
        (
            "hcp_employee_source_crosswalks",
            "fk_hcp_employee_crosswalk_prior_scope",
            "hcp_employee_source_crosswalks_prior_evidence_id_fkey",
            "hcp_employee_source_crosswalks",
            "prior_evidence_id",
        ),
        (
            "hcp_employee_source_crosswalks",
            "fk_hcp_employee_crosswalk_target_scope",
            "hcp_employee_source_crosswalks_employee_id_fkey",
            "employees",
            "employee_id",
        ),
        (
            "hcp_employee_source_crosswalks",
            "fk_hcp_employee_crosswalk_master_scope",
            "hcp_employee_source_crosswalks_master_run_id_fkey",
            "hcp_migration_master_runs",
            "master_run_id",
        ),
        (
            "hcp_customer_source_lineage",
            "fk_hcp_customer_lineage_source_scope",
            "hcp_customer_source_lineage_customer_source_identity_id_fkey",
            "customer_source_identities",
            "customer_source_identity_id",
        ),
        (
            "hcp_customer_source_lineage",
            "fk_hcp_customer_lineage_master_scope",
            "hcp_customer_source_lineage_master_run_id_fkey",
            "hcp_migration_master_runs",
            "master_run_id",
        ),
    )
    for table, scoped_name, old_name, parent, child_col in replacements:
        op.drop_constraint(scoped_name, table, type_="foreignkey")
        op.create_foreign_key(
            old_name,
            table,
            parent,
            [child_col],
            ["id"],
            ondelete="RESTRICT",
        )
    op.drop_constraint(
        "uq_hcp_hold_company", "hcp_migration_holds", type_="unique"
    )
    op.drop_constraint(
        "uq_hcp_employee_crosswalk_company",
        "hcp_employee_source_crosswalks",
        type_="unique",
    )
