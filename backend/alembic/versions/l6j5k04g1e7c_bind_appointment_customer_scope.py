"""Bind Appointments to exact Customer and Location authority.

Revision ID: l6j5k04g1e7c
Revises: k5i4j93f0d6b
"""

from collections.abc import Sequence

from alembic import op

revision: str = "l6j5k04g1e7c"
down_revision: str | Sequence[str] | None = "k5i4j93f0d6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_appointments_customer_id_customers",
        "appointments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_appointments_service_location_id_service_locations",
        "appointments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_appointments_customer_scope",
        "appointments",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_appointments_location_customer",
        "appointments",
        "service_locations",
        ["service_location_id", "customer_id"],
        ["id", "customer_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_appointments_location_customer", "appointments", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_appointments_customer_scope", "appointments", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_appointments_service_location_id_service_locations",
        "appointments",
        "service_locations",
        ["service_location_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_appointments_customer_id_customers",
        "appointments",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
