"""Protect terminal Engineering receipt, result, and decision evidence.

Revision ID: p6o4n72i9g5e
Revises: o5n3m61h8f4d
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p6o4n72i9g5e"
down_revision: str | Sequence[str] | None = "o5n3m61h8f4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "engineering_composition_receipts",
    "engineering_normalized_provider_results",
    "engineering_controlled_execution_results",
    "engineering_execution_review_decisions",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_engineering_terminal_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Engineering terminal evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION reject_engineering_terminal_evidence_mutation()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_engineering_terminal_evidence_mutation()")
