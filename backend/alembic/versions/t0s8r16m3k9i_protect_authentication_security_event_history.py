"""Protect append-only authentication security event history.

Revision ID: t0s8r16m3k9i
Revises: s9r7q05l2j8h
"""

from collections.abc import Sequence

from alembic import op

revision: str = "t0s8r16m3k9i"
down_revision: str | Sequence[str] | None = "s9r7q05l2j8h"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_authentication_security_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Authentication security event history is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_authentication_security_events_immutable
        BEFORE UPDATE OR DELETE ON authentication_security_events
        FOR EACH ROW
        EXECUTE FUNCTION reject_authentication_security_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authentication_security_events_immutable "
        "ON authentication_security_events"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_authentication_security_event_mutation()")
