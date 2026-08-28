"""Bind SOURCE.4 child runs and evidence to the HCP master rehearsal.

Revision ID: b5d9f1a3c846
Revises: a4c8e0f2b735
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "b5d9f1a3c846"
down_revision: str | Sequence[str] | None = "a4c8e0f2b735"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hcp_migration_master_runs",
        sa.Column(
            "non_applicable_counts", JSONB(), nullable=False, server_default="{}"
        ),
    )
    op.add_column(
        "hcp_migration_master_runs",
        sa.Column("child_run_ids", JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "hcp_migration_master_runs",
        sa.Column("rollback_state", JSONB(), nullable=False, server_default="{}"),
    )
    for column in ("non_applicable_counts", "child_run_ids", "rollback_state"):
        op.alter_column("hcp_migration_master_runs", column, server_default=None)
    op.create_unique_constraint(
        "uq_hcp_master_run_scope",
        "hcp_migration_master_runs",
        ["id", "company_id", "branch_id"],
    )
    op.create_unique_constraint(
        "uq_hcp_master_run_actor_scope",
        "hcp_migration_master_runs",
        ["id", "company_id", "branch_id", "actor_user_id"],
    )

    op.add_column(
        "customer_migration_runs",
        sa.Column("master_run_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_customer_run_master_scope",
        "customer_migration_runs",
        "hcp_migration_master_runs",
        ["master_run_id", "company_id", "branch_id", "initiated_by_user_id"],
        ["id", "company_id", "branch_id", "actor_user_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_customer_master_run", "customer_migration_runs", ["master_run_id"]
    )
    op.create_check_constraint(
        "ck_customer_source4_master_required",
        "customer_migration_runs",
        "source_system <> 'housecall_pro_source4' OR master_run_id IS NOT NULL",
    )

    op.add_column(
        "operational_migration_runs",
        sa.Column("master_run_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "operational_migration_runs",
        sa.Column("master_domain", sa.String(20), nullable=True),
    )
    op.create_foreign_key(
        "fk_operational_run_master_scope",
        "operational_migration_runs",
        "hcp_migration_master_runs",
        ["master_run_id", "company_id", "branch_id", "initiated_by_user_id"],
        ["id", "company_id", "branch_id", "actor_user_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_operational_master_domain",
        "operational_migration_runs",
        ["master_run_id", "master_domain"],
    )
    op.create_check_constraint(
        "ck_operational_source4_master_required",
        "operational_migration_runs",
        "source_system <> 'housecall_pro_source4' OR "
        "(master_run_id IS NOT NULL AND master_domain IN ('operational','financial'))",
    )

    op.add_column(
        "operational_migration_unlinked_estimate_evidence",
        sa.Column("master_run_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "operational_migration_unlinked_estimate_evidence",
        sa.Column(
            "synthetic_qualification",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_foreign_key(
        "fk_unlinked_estimate_master_scope",
        "operational_migration_unlinked_estimate_evidence",
        "hcp_migration_master_runs",
        ["master_run_id", "company_id", "branch_id", "recorded_by_user_id"],
        ["id", "company_id", "branch_id", "actor_user_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_unlinked_estimate_master_or_synthetic",
        "operational_migration_unlinked_estimate_evidence",
        "master_run_id IS NOT NULL OR synthetic_qualification = true",
    )
    op.alter_column(
        "operational_migration_unlinked_estimate_evidence",
        "synthetic_qualification",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_unlinked_estimate_master_or_synthetic",
        "operational_migration_unlinked_estimate_evidence",
        type_="check",
    )
    op.drop_constraint(
        "fk_unlinked_estimate_master_scope",
        "operational_migration_unlinked_estimate_evidence",
        type_="foreignkey",
    )
    op.drop_column(
        "operational_migration_unlinked_estimate_evidence",
        "synthetic_qualification",
    )
    op.drop_column("operational_migration_unlinked_estimate_evidence", "master_run_id")

    op.drop_constraint(
        "ck_operational_source4_master_required",
        "operational_migration_runs",
        type_="check",
    )
    op.drop_constraint(
        "uq_operational_master_domain", "operational_migration_runs", type_="unique"
    )
    op.drop_constraint(
        "fk_operational_run_master_scope",
        "operational_migration_runs",
        type_="foreignkey",
    )
    op.drop_column("operational_migration_runs", "master_domain")
    op.drop_column("operational_migration_runs", "master_run_id")

    op.drop_constraint(
        "ck_customer_source4_master_required",
        "customer_migration_runs",
        type_="check",
    )
    op.drop_constraint(
        "uq_customer_master_run", "customer_migration_runs", type_="unique"
    )
    op.drop_constraint(
        "fk_customer_run_master_scope",
        "customer_migration_runs",
        type_="foreignkey",
    )
    op.drop_column("customer_migration_runs", "master_run_id")

    op.drop_constraint(
        "uq_hcp_master_run_actor_scope", "hcp_migration_master_runs", type_="unique"
    )
    op.drop_constraint(
        "uq_hcp_master_run_scope", "hcp_migration_master_runs", type_="unique"
    )
    op.drop_column("hcp_migration_master_runs", "rollback_state")
    op.drop_column("hcp_migration_master_runs", "child_run_ids")
    op.drop_column("hcp_migration_master_runs", "non_applicable_counts")
