"""allow bounded current-overlay master completion

Revision ID: g7i9k1m3o5q7
Revises: f6h8j0l2n4p6
"""

import sqlalchemy as sa
from alembic import op

revision = "g7i9k1m3o5q7"
down_revision = "f6h8j0l2n4p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "hcp_migration_master_runs",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=40),
        existing_nullable=False,
    )
    op.drop_constraint(
        "ck_hcp_master_run_status", "hcp_migration_master_runs", type_="check"
    )
    op.create_check_constraint(
        "ck_hcp_master_run_status",
        "hcp_migration_master_runs",
        "status IN ('prepared','running','interrupted','completed','completed_current_operational','failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_hcp_master_run_status", "hcp_migration_master_runs", type_="check"
    )
    op.create_check_constraint(
        "ck_hcp_master_run_status",
        "hcp_migration_master_runs",
        "status IN ('prepared','running','interrupted','completed','failed')",
    )
    op.alter_column(
        "hcp_migration_master_runs",
        "status",
        existing_type=sa.String(length=40),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
