"""Protect append-only Engineering workstream event history.

Revision ID: r8q6p94k1i7g
Revises: q7p5o83j0h6f
"""

from collections.abc import Sequence

from alembic import op

revision: str = "r8q6p94k1i7g"
down_revision: str | Sequence[str] | None = "q7p5o83j0h6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER trg_engineering_workstream_events_immutable
        BEFORE UPDATE OR DELETE ON engineering_workstream_events
        FOR EACH ROW EXECUTE FUNCTION reject_engineering_event_history_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_engineering_workstream_events_immutable "
        "ON engineering_workstream_events"
    )
