"""bind Dispatch replay evidence to the canonical request

Revision ID: d2b1f49e7c0a
Revises: c1a0e38d6bfc
Create Date: 2026-08-30 16:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2b1f49e7c0a"
down_revision: str | Sequence[str] | None = "c1a0e38d6bfc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dispatch_assignment_history",
        sa.Column("request_digest", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_dispatch_history_request_digest",
        "dispatch_assignment_history",
        "request_digest IS NULL OR length(request_digest) = 64",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_dispatch_history_request_digest",
        "dispatch_assignment_history",
        type_="check",
    )
    op.drop_column("dispatch_assignment_history", "request_digest")
