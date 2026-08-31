"""Classify immutable enterprise audit mutations as integrity violations.

Revision ID: y5x3w61r8p4n
Revises: x4w2v50q7o3m
"""

from collections.abc import Sequence

from alembic import op

revision: str = "y5x3w61r8p4n"
down_revision: str | Sequence[str] | None = "x4w2v50q7o3m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_record_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit records are immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_record_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
