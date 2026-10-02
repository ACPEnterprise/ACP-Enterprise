"""Add canonical Employee phone authority.

Revision ID: uj0l2n4p6r8t
Revises: ti9k1m3o5q7s
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "uj0l2n4p6r8t"
down_revision: str | Sequence[str] | None = "ti9k1m3o5q7s"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("phone", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "phone")
