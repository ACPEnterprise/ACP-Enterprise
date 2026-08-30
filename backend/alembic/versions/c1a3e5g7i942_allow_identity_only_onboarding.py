"""Allow identity onboarding without mandatory Employee linkage.

Revision ID: c1a3e5g7i942
Revises: b0ff279c5aeb
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1a3e5g7i942"
down_revision: str | None = "b0ff279c5aeb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "identity_onboarding_requests",
        "employee_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM identity_onboarding_requests WHERE employee_id IS NULL) THEN
          RAISE EXCEPTION 'identity-only onboarding records prevent downgrade';
        END IF;
        END $$"""
    )
    op.alter_column(
        "identity_onboarding_requests",
        "employee_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
