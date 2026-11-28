"""Expand non-settlement manual payment evidence methods.

Revision ID: y4z6b8d0f2h5
Revises: x3y5z7a9c1e4
"""

from collections.abc import Sequence

from alembic import op

revision: str = "y4z6b8d0f2h5"
down_revision: str | Sequence[str] | None = "x3y5z7a9c1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_manual_payment_method",
        "invoice_manual_payment_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_manual_payment_method",
        "invoice_manual_payment_receipts",
        "payment_method IN "
        "('cash','check','ach_external','card_external','other_manual')",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM invoice_manual_payment_receipts "
        "WHERE payment_method IN ('cash','ach_external','card_external')) THEN "
        "RAISE EXCEPTION 'downgrade blocked: expanded manual payment evidence exists'; "
        "END IF; END $$"
    )
    op.drop_constraint(
        "ck_manual_payment_method",
        "invoice_manual_payment_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_manual_payment_method",
        "invoice_manual_payment_receipts",
        "payment_method IN ('check','other_manual')",
    )
