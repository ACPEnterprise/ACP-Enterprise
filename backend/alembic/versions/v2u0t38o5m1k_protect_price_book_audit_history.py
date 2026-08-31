"""Protect append-only Price Book audit history.

Revision ID: v2u0t38o5m1k
Revises: u1t9s27n4l0j
"""

from collections.abc import Sequence

from alembic import op

revision: str = "v2u0t38o5m1k"
down_revision: str | Sequence[str] | None = "u1t9s27n4l0j"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_price_book_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Price Book audit history is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_price_book_audit_entries_immutable
        BEFORE UPDATE OR DELETE ON price_book_audit_entries
        FOR EACH ROW EXECUTE FUNCTION reject_price_book_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_price_book_audit_entries_immutable "
        "ON price_book_audit_entries"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_price_book_audit_mutation()")
