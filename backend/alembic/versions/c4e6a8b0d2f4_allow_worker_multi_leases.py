"""allow worker leases up to configured capacity

Revision ID: c4e6a8b0d2f4
Revises: b2d4f6h8j0l2
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e6a8b0d2f4"
down_revision = "b2d4f6h8j0l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "uq_worker_leases_active_worker", table_name="engineering_worker_leases"
    )


def downgrade() -> None:
    op.create_index(
        "uq_worker_leases_active_worker",
        "engineering_worker_leases",
        ["company_id", "worker_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
