"""Converge current protected and Operations migration lineages."""

from collections.abc import Sequence

revision: str = "pe470p2q2r3s4"
down_revision: str | Sequence[str] | None = (
    "p2r4t6v8x1z3",
    "q2s4u6w8y0a2",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
