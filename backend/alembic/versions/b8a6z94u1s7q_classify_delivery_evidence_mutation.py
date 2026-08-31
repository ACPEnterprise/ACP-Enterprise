"""Classify immutable delivery evidence mutations as integrity violations.

Revision ID: b8a6z94u1s7q
Revises: a7z5y83t0r6p
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8a6z94u1s7q"
down_revision: str | Sequence[str] | None = "a7z5y83t0r6p"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_business_event_delivery_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Business Event delivery evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_notification_delivery_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Notification delivery evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_business_event_delivery_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Business Event delivery evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_notification_delivery_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Notification delivery evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
