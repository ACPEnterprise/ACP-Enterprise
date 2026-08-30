"""Bind Payment Intent Customer and Invoice identities to tenant scope.

Revision ID: h6f5d04c1a7e
Revises: g5e4c93b0f6d
"""

from collections.abc import Sequence

from alembic import op

revision: str = "h6f5d04c1a7e"
down_revision: str | None = "g5e4c93b0f6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_customers_company_id_id", "customers", ["company_id", "id"]
    )
    op.drop_constraint(
        "payment_intents_customer_id_fkey", "payment_intents", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_payment_intents_customer_scope",
        "payment_intents",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_intents_invoice_scope",
        "payment_intents",
        "invoices",
        ["company_id", "branch_id", "invoice_id", "customer_id"],
        ["company_id", "branch_id", "id", "customer_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payment_intents_invoice_scope", "payment_intents", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_payment_intents_customer_scope", "payment_intents", type_="foreignkey"
    )
    op.create_foreign_key(
        "payment_intents_customer_id_fkey",
        "payment_intents",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_customers_company_id_id", "customers", type_="unique")
