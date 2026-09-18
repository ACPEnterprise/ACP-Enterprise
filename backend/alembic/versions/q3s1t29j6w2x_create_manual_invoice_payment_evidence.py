"""create manual invoice payment evidence

Revision ID: q3s1t29j6w2x
Revises: p2r0s28i5v1w
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q3s1t29j6w2x"
down_revision: str | Sequence[str] | None = "p2r0s28i5v1w"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoice_manual_payment_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("payment_method", sa.String(24), nullable=False),
        sa.Column("reference_label", sa.String(32), nullable=False),
        sa.Column("reference_digest", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settlement_state", sa.String(24), nullable=False),
        sa.Column("accounting_state", sa.String(24), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "payment_method IN ('check','other_manual')",
            name="ck_manual_payment_method",
        ),
        sa.CheckConstraint("amount > 0", name="ck_manual_payment_amount"),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_manual_payment_currency"
        ),
        sa.CheckConstraint(
            "settlement_state = 'not_asserted'",
            name="ck_manual_payment_settlement",
        ),
        sa.CheckConstraint(
            "accounting_state = 'not_posted'", name="ck_manual_payment_accounting"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_manual_payment_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_manual_payment_invoice",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_manual_payment_command"
        ),
        sa.UniqueConstraint(
            "company_id", "reference_digest", name="uq_manual_payment_reference"
        ),
    )
    op.create_index(
        "ix_manual_payment_invoice_time",
        "invoice_manual_payment_receipts",
        ["company_id", "invoice_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_manual_payment_invoice_time",
        table_name="invoice_manual_payment_receipts",
    )
    op.drop_table("invoice_manual_payment_receipts")
