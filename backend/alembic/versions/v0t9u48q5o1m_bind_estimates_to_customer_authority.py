"""Bind Estimate customer and location authority.

Revision ID: v0t9u48q5o1m
Revises: u9s8t37p4n0l
"""

from collections.abc import Sequence

from alembic import op

revision: str = "v0t9u48q5o1m"
down_revision: str | Sequence[str] | None = "u9s8t37p4n0l"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("estimates_customer_id_fkey", "estimates", type_="foreignkey")
    op.drop_constraint(
        "estimates_service_location_id_fkey", "estimates", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_legacy_estimates_customer_scope",
        "estimates",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_legacy_estimates_location_customer",
        "estimates",
        "service_locations",
        ["service_location_id", "customer_id"],
        ["id", "customer_id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "estimate_proposals_customer_id_fkey", "estimate_proposals", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_estimate_proposals_customer_scope",
        "estimate_proposals",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_estimate_proposals_customer_scope", "estimate_proposals", type_="foreignkey"
    )
    op.create_foreign_key(
        "estimate_proposals_customer_id_fkey",
        "estimate_proposals",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_legacy_estimates_location_customer", "estimates", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_legacy_estimates_customer_scope", "estimates", type_="foreignkey"
    )
    op.create_foreign_key(
        "estimates_service_location_id_fkey",
        "estimates",
        "service_locations",
        ["service_location_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "estimates_customer_id_fkey",
        "estimates",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
