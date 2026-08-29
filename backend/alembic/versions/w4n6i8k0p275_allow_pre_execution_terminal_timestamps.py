"""allow truthful pre-execution terminal timestamps

Revision ID: w4n6i8k0p275
Revises: v3m5i7k9n164
"""

from collections.abc import Sequence

from alembic import op

revision: str = "w4n6i8k0p275"
down_revision: str | Sequence[str] | None = "v3m5i7k9n164"
branch_labels = None
depends_on = None


OLD_CONSTRAINT = (
    "started_at IS NULL AND finished_at IS NULL "
    "OR started_at IS NOT NULL AND "
    "(finished_at IS NULL OR finished_at >= started_at)"
)

NEW_CONSTRAINT = (
    "(started_at IS NULL AND "
    "(finished_at IS NULL OR "
    "(state IN ('failed','cancelled') AND finished_at >= requested_at))) "
    "OR (started_at IS NOT NULL AND started_at >= requested_at AND "
    "(finished_at IS NULL OR finished_at >= started_at))"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_engineering_executions_timestamps",
        "engineering_executions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_engineering_executions_timestamps",
        "engineering_executions",
        NEW_CONSTRAINT,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_engineering_executions_timestamps",
        "engineering_executions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_engineering_executions_timestamps",
        "engineering_executions",
        OLD_CONSTRAINT,
    )
