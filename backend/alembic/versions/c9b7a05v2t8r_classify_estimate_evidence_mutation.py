"""Classify immutable Estimate evidence mutations as integrity violations.

Revision ID: c9b7a05v2t8r
Revises: b8a6z94u1s7q
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c9b7a05v2t8r"
down_revision: str | Sequence[str] | None = "b8a6z94u1s7q"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_estimate_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'estimate revision evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_estimate_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'estimate revision evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
