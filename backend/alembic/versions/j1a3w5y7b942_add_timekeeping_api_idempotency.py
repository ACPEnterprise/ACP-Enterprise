"""add Timekeeping API idempotency evidence

Revision ID: j1a3w5y7b942
Revises: i0z2v4x6a831
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "j1a3w5y7b942"
down_revision: str | Sequence[str] | None = "i0z2v4x6a831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "timekeeping_punch_events",
        sa.Column("idempotency_key", sa.String(128)),
    )
    op.add_column(
        "timekeeping_punch_events",
        sa.Column("request_digest", sa.String(64)),
    )
    op.execute(
        "UPDATE timekeeping_punch_events SET request_digest = event_digest "
        "WHERE request_digest IS NULL"
    )
    op.alter_column(
        "timekeeping_punch_events", "request_digest", nullable=False
    )
    op.create_unique_constraint(
        "uq_time_punch_idempotency",
        "timekeeping_punch_events",
        ["company_id", "recorded_by_user_id", "idempotency_key"],
    )
    op.add_column(
        "timekeeping_entry_revisions",
        sa.Column("origin_idempotency_key", sa.String(128)),
    )
    op.add_column(
        "timekeeping_entry_revisions",
        sa.Column("origin_request_digest", sa.String(64)),
    )
    op.create_index(
        "uq_time_manual_idempotency",
        "timekeeping_entry_revisions",
        ["company_id", "responsible_user_id", "origin_idempotency_key"],
        unique=True,
        postgresql_where=sa.text(
            "revision_number = 1 AND origin_idempotency_key IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_time_manual_idempotency", table_name="timekeeping_entry_revisions"
    )
    op.drop_column("timekeeping_entry_revisions", "origin_request_digest")
    op.drop_column("timekeeping_entry_revisions", "origin_idempotency_key")
    op.drop_constraint(
        "uq_time_punch_idempotency",
        "timekeeping_punch_events",
        type_="unique",
    )
    op.drop_column("timekeeping_punch_events", "request_digest")
    op.drop_column("timekeeping_punch_events", "idempotency_key")
