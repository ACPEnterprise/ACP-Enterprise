"""Bind Payment receipt, refund, and deposit lineage.

Revision ID: a1z9y27t4r0p
Revises: z0y8x16s3q9o
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1z9y27t4r0p"
down_revision: str | Sequence[str] | None = "z0y8x16s3q9o"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_payment_intents_receipt_scope",
        "payment_intents",
        ["company_id", "id", "branch_id", "customer_id", "currency"],
    )
    op.drop_constraint(
        "payment_receipts_company_id_intent_id_fkey",
        "payment_receipts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_payment_receipts_intent_scope",
        "payment_receipts",
        "payment_intents",
        ["company_id", "intent_id", "branch_id", "customer_id", "currency"],
        ["company_id", "id", "branch_id", "customer_id", "currency"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_payment_receipts_child_scope",
        "payment_receipts",
        ["company_id", "id", "branch_id", "currency"],
    )

    op.drop_constraint(
        "payment_refunds_company_id_receipt_id_fkey",
        "payment_refunds",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_payment_refunds_receipt_scope",
        "payment_refunds",
        "payment_receipts",
        ["company_id", "receipt_id", "branch_id", "currency"],
        ["company_id", "id", "branch_id", "currency"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_refunds_requested_by_user",
        "payment_refunds",
        "users",
        ["requested_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_refunds_approved_by_user",
        "payment_refunds",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_payment_deposits_branch_scope",
        "payment_deposits",
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_deposits_prepared_by_user",
        "payment_deposits",
        "users",
        ["prepared_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_deposits_approved_by_user",
        "payment_deposits",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_payment_deposits_receipt_scope",
        "payment_deposits",
        ["company_id", "id", "branch_id", "currency"],
    )

    op.add_column(
        "payment_deposit_receipts", sa.Column("branch_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "payment_deposit_receipts",
        sa.Column("currency", sa.String(length=3), nullable=True),
    )
    op.execute(
        "UPDATE payment_deposit_receipts AS dr "
        "SET branch_id = d.branch_id, currency = d.currency "
        "FROM payment_deposits AS d "
        "WHERE d.company_id = dr.company_id AND d.id = dr.deposit_id"
    )
    op.alter_column("payment_deposit_receipts", "branch_id", nullable=False)
    op.alter_column("payment_deposit_receipts", "currency", nullable=False)
    op.drop_constraint(
        "payment_deposit_receipts_company_id_deposit_id_fkey",
        "payment_deposit_receipts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "payment_deposit_receipts_company_id_receipt_id_fkey",
        "payment_deposit_receipts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_payment_deposit_receipts_deposit_scope",
        "payment_deposit_receipts",
        "payment_deposits",
        ["company_id", "deposit_id", "branch_id", "currency"],
        ["company_id", "id", "branch_id", "currency"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payment_deposit_receipts_receipt_scope",
        "payment_deposit_receipts",
        "payment_receipts",
        ["company_id", "receipt_id", "branch_id", "currency"],
        ["company_id", "id", "branch_id", "currency"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payment_deposit_receipts_receipt_scope",
        "payment_deposit_receipts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_deposit_receipts_deposit_scope",
        "payment_deposit_receipts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "payment_deposit_receipts_company_id_receipt_id_fkey",
        "payment_deposit_receipts",
        "payment_receipts",
        ["company_id", "receipt_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "payment_deposit_receipts_company_id_deposit_id_fkey",
        "payment_deposit_receipts",
        "payment_deposits",
        ["company_id", "deposit_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_column("payment_deposit_receipts", "currency")
    op.drop_column("payment_deposit_receipts", "branch_id")

    op.drop_constraint(
        "uq_payment_deposits_receipt_scope", "payment_deposits", type_="unique"
    )
    op.drop_constraint(
        "fk_payment_deposits_approved_by_user",
        "payment_deposits",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_deposits_prepared_by_user",
        "payment_deposits",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_deposits_branch_scope",
        "payment_deposits",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_payment_refunds_approved_by_user",
        "payment_refunds",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_refunds_requested_by_user",
        "payment_refunds",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_refunds_receipt_scope",
        "payment_refunds",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "payment_refunds_company_id_receipt_id_fkey",
        "payment_refunds",
        "payment_receipts",
        ["company_id", "receipt_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "uq_payment_receipts_child_scope", "payment_receipts", type_="unique"
    )
    op.drop_constraint(
        "fk_payment_receipts_intent_scope",
        "payment_receipts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "payment_receipts_company_id_intent_id_fkey",
        "payment_receipts",
        "payment_intents",
        ["company_id", "intent_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_payment_intents_receipt_scope", "payment_intents", type_="unique"
    )
