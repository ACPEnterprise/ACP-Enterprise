"""Protect immutable Price Book commercial snapshots.

Revision ID: x4w2v50q7o3m
Revises: w3v1u49p6n2l
"""

from collections.abc import Sequence

from alembic import op

revision: str = "x4w2v50q7o3m"
down_revision: str | Sequence[str] | None = "w3v1u49p6n2l"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_price_book_snapshot_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Price Book commercial snapshot is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_price_book_commercial_snapshots_immutable
        BEFORE UPDATE OR DELETE ON price_book_commercial_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_price_book_snapshot_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_price_book_commercial_snapshots_immutable "
        "ON price_book_commercial_snapshots"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_price_book_snapshot_mutation()")
