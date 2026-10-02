"""merge bank matching and release actor heads

Revision ID: bn3t5e7q9d1w
Revises: bm2s4d6p8c0v, tq0f2h4j6l8n
"""

from collections.abc import Sequence

revision: str = "bn3t5e7q9d1w"
down_revision: str | Sequence[str] | None = (
    "bm2s4d6p8c0v",
    "tq0f2h4j6l8n",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
