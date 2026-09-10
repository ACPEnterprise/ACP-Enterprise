"""Add replay-safe audited Timekeeping correction classification.

Revision ID: c3e5g7i9k1m3
Revises: c2e4g6i8k0m2
"""

import sqlalchemy as sa

from alembic import op

revision = "c3e5g7i9k1m3"
down_revision = "c2e4g6i8k0m2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "timekeeping_entry_revisions",
        sa.Column("correction_kind", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "timekeeping_entry_revisions",
        sa.Column("correction_idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "timekeeping_entry_revisions",
        sa.Column("correction_request_digest", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_time_entry_correction_kind",
        "timekeeping_entry_revisions",
        "correction_kind IS NULL OR correction_kind IN ("
        "'missing_clock_out','incorrect_job','missing_interval',"
        "'overlapping_intervals','incorrect_start','incorrect_stop')",
    )
    op.create_index(
        "uq_time_correction_idempotency",
        "timekeeping_entry_revisions",
        ["company_id", "responsible_user_id", "correction_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("correction_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_time_correction_idempotency", table_name="timekeeping_entry_revisions"
    )
    op.drop_constraint(
        "ck_time_entry_correction_kind",
        "timekeeping_entry_revisions",
        type_="check",
    )
    op.drop_column("timekeeping_entry_revisions", "correction_request_digest")
    op.drop_column("timekeeping_entry_revisions", "correction_idempotency_key")
    op.drop_column("timekeeping_entry_revisions", "correction_kind")
