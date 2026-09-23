"""Create durable Payroll close authority for Issue #449."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "pa449c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "p2r4t6v8x1z3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payroll_run_close_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prior_run_digest", sa.String(length=64), nullable=False),
        sa.Column("close_state", sa.String(length=16), nullable=False),
        sa.Column("close_version", sa.Integer(), nullable=False),
        sa.Column("closed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_reason", sa.Text(), nullable=False),
        sa.Column("register_digest", sa.String(length=64), nullable=False),
        sa.Column("replay_identity", sa.String(length=160), nullable=False),
        sa.Column("close_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "run_id"], ["payroll_runs.company_id", "payroll_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "run_id", name="uq_payroll_run_close_company_run"),
        sa.UniqueConstraint("company_id", "replay_identity", name="uq_payroll_run_close_replay"),
        sa.UniqueConstraint("company_id", "close_digest", name="uq_payroll_run_close_digest"),
        sa.CheckConstraint("close_state = 'closed'", name="ck_payroll_run_close_state"),
    )


def downgrade() -> None:
    op.drop_table("payroll_run_close_records")
