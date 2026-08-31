"""Protect repository authorization and operation event history from mutation.

Revision ID: o5n3m61h8f4d
Revises: n4m2l50g7e3c
"""

from collections.abc import Sequence

from alembic import op

revision: str = "o5n3m61h8f4d"
down_revision: str | Sequence[str] | None = "n4m2l50g7e3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_repository_event_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Repository lifecycle event history is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "engineering_repository_authorization_events",
        "engineering_repository_operation_events",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION reject_repository_event_history_mutation()"
        )


def downgrade() -> None:
    for table in (
        "engineering_repository_operation_events",
        "engineering_repository_authorization_events",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_repository_event_history_mutation()")
