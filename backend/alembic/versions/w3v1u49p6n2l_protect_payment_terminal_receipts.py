"""Protect terminal Payment receipt evidence from mutation.

Revision ID: w3v1u49p6n2l
Revises: v2u0t38o5m1k
"""

from collections.abc import Sequence

from alembic import op

revision: str = "w3v1u49p6n2l"
down_revision: str | Sequence[str] | None = "v2u0t38o5m1k"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "payment_deposit_receipts",
    "payment_webhook_receipts",
    "payment_accounting_posting_receipts",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_payment_terminal_receipt_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Payment terminal receipt evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in _TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_payment_terminal_receipt_mutation()
            """
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_payment_terminal_receipt_mutation()")
