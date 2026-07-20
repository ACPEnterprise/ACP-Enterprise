"""add user email verification state

Revision ID: a6c9e1f4b830
Revises: f5b8d0c3e729
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6c9e1f4b830"
down_revision: Union[str, Sequence[str], None] = "f5b8d0c3e729"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
