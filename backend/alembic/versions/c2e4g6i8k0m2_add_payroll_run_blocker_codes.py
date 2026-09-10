"""Preserve exact Payroll run-member blocker codes.

Revision ID: c2e4g6i8k0m2
Revises: b2d4f6h8j0m3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c2e4g6i8k0m2"
down_revision: str | Sequence[str] | None = "b2d4f6h8j0m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payroll_run_members",
        sa.Column(
            "blocker_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("payroll_run_members", "blocker_codes")
