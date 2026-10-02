"""add explicit bank matching lineage

Revision ID: bm2s4d6p8c0v
Revises: bk1r3c5n7a9t
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "bm2s4d6p8c0v"
down_revision: str | Sequence[str] | None = "bk1r3c5n7a9t"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounting_bank_transactions",
        sa.Column("related_identity", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "accounting_bank_transactions",
        sa.Column("group_key", sa.String(length=240), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounting_bank_transactions", "group_key")
    op.drop_column("accounting_bank_transactions", "related_identity")
