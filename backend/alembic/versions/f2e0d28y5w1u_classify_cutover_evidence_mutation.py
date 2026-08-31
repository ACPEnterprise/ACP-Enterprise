"""Classify immutable cutover evidence mutations as integrity violations.

Revision ID: f2e0d28y5w1u
Revises: e1d9c27x4v0t
"""

from alembic import op

revision = "f2e0d28y5w1u"
down_revision = "e1d9c27x4v0t"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_cutover_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'cutover planning evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_cutover_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'cutover planning evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
