"""Complete operational Job clock evidence.

Revision ID: d4f6h8j0l2n4
Revises: c3e5g7i9k1m3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4f6h8j0l2n4"
down_revision: str | Sequence[str] | None = "c3e5g7i9k1m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "timekeeping_job_interval_revisions",
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE timekeeping_job_interval_revisions "
        "SET duration_seconds = duration_minutes * 60"
    )
    op.alter_column(
        "timekeeping_job_interval_revisions", "duration_seconds", nullable=False
    )
    op.drop_constraint(
        "ck_job_interval_duration",
        "timekeeping_job_interval_revisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_job_interval_duration",
        "timekeeping_job_interval_revisions",
        "duration_minutes >= 0",
    )
    op.create_check_constraint(
        "ck_job_interval_duration_seconds",
        "timekeeping_job_interval_revisions",
        "duration_seconds > 0",
    )
    op.add_column(
        "timekeeping_job_interval_revisions",
        sa.Column("correction_idempotency_key", sa.String(128)),
    )
    op.add_column(
        "timekeeping_job_interval_revisions",
        sa.Column("correction_request_digest", sa.String(64)),
    )
    op.create_index(
        "uq_job_interval_correction_idempotency",
        "timekeeping_job_interval_revisions",
        ["company_id", "corrected_by_user_id", "correction_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("correction_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_job_interval_correction_idempotency",
        table_name="timekeeping_job_interval_revisions",
    )
    op.drop_column("timekeeping_job_interval_revisions", "correction_request_digest")
    op.drop_column("timekeeping_job_interval_revisions", "correction_idempotency_key")
    op.drop_constraint(
        "ck_job_interval_duration_seconds",
        "timekeeping_job_interval_revisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_job_interval_duration",
        "timekeeping_job_interval_revisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_job_interval_duration",
        "timekeeping_job_interval_revisions",
        "duration_minutes > 0",
    )
    op.drop_column("timekeeping_job_interval_revisions", "duration_seconds")
