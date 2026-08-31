"""Bind Customer Migration source identities to exact run lineage.

Revision ID: x2v1w60s7q3o
Revises: w1u0v59r6p2n
"""

from collections.abc import Sequence

from alembic import op

revision: str = "x2v1w60s7q3o"
down_revision: str | Sequence[str] | None = "w1u0v59r6p2n"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_customer_migration_runs_company_id",
        "customer_migration_runs",
        ["company_id", "id"],
    )
    op.create_unique_constraint(
        "uq_customer_migration_runs_branch_id",
        "customer_migration_runs",
        ["company_id", "branch_id", "id"],
    )
    op.drop_constraint(
        "customer_migration_runs_branch_id_fkey",
        "customer_migration_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_customer_migration_runs_branch_scope",
        "customer_migration_runs",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    for old_name in (
        "customer_source_identities_branch_id_fkey",
        "customer_source_identities_customer_id_fkey",
        "customer_source_identities_first_run_id_fkey",
    ):
        op.drop_constraint(old_name, "customer_source_identities", type_="foreignkey")
    op.create_foreign_key(
        "fk_customer_source_identity_branch_scope",
        "customer_source_identities",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_customer_source_identity_customer_scope",
        "customer_source_identities",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_customer_source_identity_first_run_scope",
        "customer_source_identities",
        "customer_migration_runs",
        ["company_id", "branch_id", "first_run_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )

    for table, old_name, new_name in (
        (
            "customer_contact_source_identities",
            "customer_contact_source_identities_first_run_id_fkey",
            "fk_contact_source_identity_first_run_scope",
        ),
        (
            "service_location_source_identities",
            "service_location_source_identities_first_run_id_fkey",
            "fk_location_source_identity_first_run_scope",
        ),
    ):
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name,
            table,
            "customer_migration_runs",
            ["company_id", "first_run_id"],
            ["company_id", "id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for table, old_name, new_name in (
        (
            "service_location_source_identities",
            "service_location_source_identities_first_run_id_fkey",
            "fk_location_source_identity_first_run_scope",
        ),
        (
            "customer_contact_source_identities",
            "customer_contact_source_identities_first_run_id_fkey",
            "fk_contact_source_identity_first_run_scope",
        ),
    ):
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(
            old_name,
            table,
            "customer_migration_runs",
            ["first_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    for name in (
        "fk_customer_source_identity_first_run_scope",
        "fk_customer_source_identity_customer_scope",
        "fk_customer_source_identity_branch_scope",
    ):
        op.drop_constraint(name, "customer_source_identities", type_="foreignkey")
    op.create_foreign_key(
        "customer_source_identities_first_run_id_fkey",
        "customer_source_identities",
        "customer_migration_runs",
        ["first_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "customer_source_identities_customer_id_fkey",
        "customer_source_identities",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "customer_source_identities_branch_id_fkey",
        "customer_source_identities",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_customer_migration_runs_branch_scope",
        "customer_migration_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "customer_migration_runs_branch_id_fkey",
        "customer_migration_runs",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_customer_migration_runs_branch_id",
        "customer_migration_runs",
        type_="unique",
    )
    op.drop_constraint(
        "uq_customer_migration_runs_company_id",
        "customer_migration_runs",
        type_="unique",
    )
