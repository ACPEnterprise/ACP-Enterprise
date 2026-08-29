"""Bind SOURCE.4 history persistence to the HCP master rehearsal.

Revision ID: d7f1b3c5e068
Revises: c6e0a2b4d957
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d7f1b3c5e068"
down_revision: str | Sequence[str] | None = "c6e0a2b4d957"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_operational_source4_master_required",
        "operational_migration_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_source4_master_required",
        "operational_migration_runs",
        "source_system <> 'housecall_pro_source4' OR "
        "(master_run_id IS NOT NULL AND "
        "master_domain IN ('operational','financial','history'))",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_operational_source4_master_required",
        "operational_migration_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_source4_master_required",
        "operational_migration_runs",
        "source_system <> 'housecall_pro_source4' OR "
        "(master_run_id IS NOT NULL AND "
        "master_domain IN ('operational','financial'))",
    )
