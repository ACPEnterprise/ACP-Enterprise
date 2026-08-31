"""Classify posted Accounting mutations as integrity violations.

Revision ID: a7z5y83t0r6p
Revises: z6y4x72s9q5o
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7z5y83t0r6p"
down_revision: str | Sequence[str] | None = "z6y4x72s9q5o"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION accounting_reject_posted_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'posted' THEN
                RAISE EXCEPTION 'posted accounting journals are immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION accounting_reject_posted_line_mutation()
        RETURNS trigger AS $$
        DECLARE target_journal_id uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                target_journal_id := NEW.journal_id;
            ELSE
                target_journal_id := OLD.journal_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM accounting_journals j
                WHERE j.id = target_journal_id AND j.status = 'posted'
            ) THEN
                RAISE EXCEPTION 'posted accounting journal lines are immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION accounting_reject_posted_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'posted' THEN
                RAISE EXCEPTION 'posted accounting journals are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION accounting_reject_posted_line_mutation()
        RETURNS trigger AS $$
        DECLARE target_journal_id uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                target_journal_id := NEW.journal_id;
            ELSE
                target_journal_id := OLD.journal_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM accounting_journals j
                WHERE j.id = target_journal_id AND j.status = 'posted'
            ) THEN
                RAISE EXCEPTION 'posted accounting journal lines are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
