"""Protect append-only Engineering event, evidence, and receipt history.

Revision ID: q7p5o83j0h6f
Revises: p6o4n72i9g5e
"""

from collections.abc import Sequence

from alembic import op

revision: str = "q7p5o83j0h6f"
down_revision: str | Sequence[str] | None = "p6o4n72i9g5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "engineering_capacity_events",
    "engineering_command_events",
    "engineering_external_milestone_evidence",
    "engineering_milestone_events",
    "engineering_provider_progress_events",
    "engineering_scheduler_events",
    "engineering_worker_transport_receipts",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_engineering_event_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Engineering event history is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION reject_engineering_event_history_mutation()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_engineering_event_history_mutation()")
