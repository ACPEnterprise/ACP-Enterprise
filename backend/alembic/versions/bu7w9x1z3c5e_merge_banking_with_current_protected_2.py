"""Merge the Banking closure line with the latest protected schema head.

Revision ID: bu7w9x1z3c5e
Revises: bt5v7x9z1c3e, vl2n4p6r8t0v
"""

from collections.abc import Sequence


revision: str = "bu7w9x1z3c5e"
down_revision: str | Sequence[str] | None = ("bt5v7x9z1c3e", "vl2n4p6r8t0v")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
