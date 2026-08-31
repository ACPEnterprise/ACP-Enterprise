"""Protect complete Business Event history from update and delete.

Revision ID: s9r7q05l2j8h
Revises: r8q6p94k1i7g
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s9r7q05l2j8h"
down_revision: str | Sequence[str] | None = "r8q6p94k1i7g"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TRIGGER trg_business_event_scope_immutable ON business_events")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_business_event_scope_identity()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Business Event history is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_business_event_scope_immutable
        BEFORE UPDATE OR DELETE ON business_events
        FOR EACH ROW EXECUTE FUNCTION protect_business_event_scope_identity()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_business_event_scope_immutable ON business_events")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_business_event_scope_identity()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.company_id IS DISTINCT FROM OLD.company_id
               OR NEW.branch_id IS DISTINCT FROM OLD.branch_id THEN
                RAISE EXCEPTION 'Business Event scope is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_business_event_scope_immutable
        BEFORE UPDATE ON business_events
        FOR EACH ROW EXECUTE FUNCTION protect_business_event_scope_identity()
        """
    )
