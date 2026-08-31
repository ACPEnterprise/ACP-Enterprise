"""Bind Invoice, AR, and replay evidence to exact tenant lineage.

Revision ID: u9s8t37p4n0l
Revises: t8r7s26o3m9k
"""

from collections.abc import Sequence

from alembic import op

revision: str = "u9s8t37p4n0l"
down_revision: str | Sequence[str] | None = "t8r7s26o3m9k"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("invoices_customer_id_fkey", "invoices", type_="foreignkey")
    op.create_foreign_key(
        "fk_invoices_customer_scope",
        "invoices",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("fk_ar_entries_invoice", "ar_ledger_entries", type_="foreignkey")
    op.drop_constraint(
        "ar_ledger_entries_customer_id_fkey", "ar_ledger_entries", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_ar_entries_invoice_scope",
        "ar_ledger_entries",
        "invoices",
        ["company_id", "branch_id", "invoice_id", "customer_id"],
        ["company_id", "branch_id", "id", "customer_id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "invoice_idempotency_invoice_id_fkey", "invoice_idempotency", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_invoice_idempotency_invoice_scope",
        "invoice_idempotency",
        "invoices",
        ["company_id", "invoice_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "invoice_payment_receipt_evidence_customer_id_fkey",
        "invoice_payment_receipt_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_invoice_receipts_customer_scope",
        "invoice_payment_receipt_evidence",
        "customers",
        ["company_id", "customer_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_invoice_receipts_customer_scope",
        "invoice_payment_receipt_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "invoice_payment_receipt_evidence_customer_id_fkey",
        "invoice_payment_receipt_evidence",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_invoice_idempotency_invoice_scope", "invoice_idempotency", type_="foreignkey"
    )
    op.create_foreign_key(
        "invoice_idempotency_invoice_id_fkey",
        "invoice_idempotency",
        "invoices",
        ["invoice_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_ar_entries_invoice_scope", "ar_ledger_entries", type_="foreignkey"
    )
    op.create_foreign_key(
        "ar_ledger_entries_customer_id_fkey",
        "ar_ledger_entries",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_ar_entries_invoice",
        "ar_ledger_entries",
        "invoices",
        ["company_id", "invoice_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("fk_invoices_customer_scope", "invoices", type_="foreignkey")
    op.create_foreign_key(
        "invoices_customer_id_fkey",
        "invoices",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
