"""merge Banking closure with the current protected schema head

Revision ID: bt5v7x9z1c3e
Revises: br4u6f8h0j2l, uk1m3o5q7s9u
"""

from collections.abc import Sequence


revision: str = "bt5v7x9z1c3e"
down_revision: str | Sequence[str] | None = ("br4u6f8h0j2l", "uk1m3o5q7s9u")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
