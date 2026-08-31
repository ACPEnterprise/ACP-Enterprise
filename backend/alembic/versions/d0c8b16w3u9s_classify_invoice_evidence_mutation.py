"""Classify immutable Invoice financial evidence mutations.

Revision ID: d0c8b16w3u9s
Revises: c9b7a05v2t8r
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d0c8b16w3u9s"
down_revision: str | Sequence[str] | None = "c9b7a05v2t8r"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_invoice_financial_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'invoice financial evidence is append-only'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_invoice_financial_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'invoice financial evidence is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
