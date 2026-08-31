"""Bind Jobs to exact customer and location authority.

Revision ID: w1u0v59r6p2n
Revises: v0t9u48q5o1m
"""

from collections.abc import Sequence

from alembic import op

revision: str = "w1u0v59r6p2n"
down_revision: str | Sequence[str] | None = "v0t9u48q5o1m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("fk_jobs_customer_id_customers", "jobs", type_="foreignkey")
    op.drop_constraint(
        "fk_jobs_service_location_id_service_locations", "jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_jobs_customer_scope",
        "jobs",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_jobs_location_customer",
        "jobs",
        "service_locations",
        ["service_location_id", "customer_id"],
        ["id", "customer_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_location_customer", "jobs", type_="foreignkey")
    op.drop_constraint("fk_jobs_customer_scope", "jobs", type_="foreignkey")
    op.create_foreign_key(
        "fk_jobs_service_location_id_service_locations",
        "jobs",
        "service_locations",
        ["service_location_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_jobs_customer_id_customers",
        "jobs",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
