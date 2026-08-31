"""Classify immutable repository event mutations as integrity violations.

Revision ID: z6y4x72s9q5o
Revises: y5x3w61r8p4n
"""

from collections.abc import Sequence

from alembic import op

revision: str = "z6y4x72s9q5o"
down_revision: str | Sequence[str] | None = "y5x3w61r8p4n"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_repository_event_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Repository lifecycle event history is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_repository_event_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Repository lifecycle event history is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
