"""amend Job lifecycle history constraints

Revision ID: c6a1d3e5f709
Revises: b4e7c9d1f305
"""

from collections.abc import Sequence

from alembic import op


revision: str = "c6a1d3e5f709"
down_revision: str | None = "b4e7c9d1f305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_start_state", "jobs", type_="check")
    op.drop_constraint("ck_jobs_completion_state", "jobs", type_="check")
    op.drop_constraint("ck_jobs_cancellation_state", "jobs", type_="check")

    op.create_check_constraint(
        "ck_jobs_start_state",
        "jobs",
        "(status = 'draft' AND started_at IS NULL) OR "
        "(status IN ('in_progress', 'paused', 'completed') "
        "AND started_at IS NOT NULL) OR status IN ('ready', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_jobs_completion_state",
        "jobs",
        "((completed_at IS NULL AND completed_by_user_id IS NULL) OR "
        "(completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL)) AND "
        "(status <> 'completed' OR (completed_at IS NOT NULL "
        "AND completed_by_user_id IS NOT NULL))",
    )
    op.create_check_constraint(
        "ck_jobs_cancellation_state",
        "jobs",
        "((cancelled_at IS NULL AND cancelled_by_user_id IS NULL "
        "AND cancellation_reason_code IS NULL) OR "
        "(cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL "
        "AND cancellation_reason_code IS NOT NULL)) AND "
        "(status <> 'cancelled' OR (cancelled_at IS NOT NULL "
        "AND cancelled_by_user_id IS NOT NULL "
        "AND cancellation_reason_code IS NOT NULL))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_jobs_cancellation_state", "jobs", type_="check")
    op.drop_constraint("ck_jobs_completion_state", "jobs", type_="check")
    op.drop_constraint("ck_jobs_start_state", "jobs", type_="check")

    op.create_check_constraint(
        "ck_jobs_start_state",
        "jobs",
        "(status IN ('in_progress', 'paused', 'completed') "
        "AND started_at IS NOT NULL) OR "
        "(status IN ('draft', 'ready') AND started_at IS NULL) OR "
        "status = 'cancelled'",
    )
    op.create_check_constraint(
        "ck_jobs_completion_state",
        "jobs",
        "(status = 'completed' AND completed_at IS NOT NULL "
        "AND completed_by_user_id IS NOT NULL) OR "
        "(status <> 'completed' AND completed_at IS NULL "
        "AND completed_by_user_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_jobs_cancellation_state",
        "jobs",
        "(status = 'cancelled' AND cancelled_at IS NOT NULL "
        "AND cancelled_by_user_id IS NOT NULL "
        "AND cancellation_reason_code IS NOT NULL) OR "
        "(status <> 'cancelled' AND cancelled_at IS NULL "
        "AND cancelled_by_user_id IS NULL "
        "AND cancellation_reason_code IS NULL)",
    )
