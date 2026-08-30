"""merge Supply Chain and OM2-C quality heads

Revision ID: e3c2a71f8d4b
Revises: 19i4k89084j8, d2b1f49e7c0a
"""

from collections.abc import Sequence

revision: str = "e3c2a71f8d4b"
down_revision: str | Sequence[str] | None = (
    "19i4k89084j8",
    "d2b1f49e7c0a",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
