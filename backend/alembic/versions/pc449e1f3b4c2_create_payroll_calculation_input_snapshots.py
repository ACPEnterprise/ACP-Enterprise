"""Create immutable Payroll calculation-input snapshot authority."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "pc449e1f3b4c2"
down_revision: Union[str, Sequence[str], None] = "pb449d0e2f3a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payroll_calculation_input_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("run_digest", sa.String(64), nullable=False),
        sa.Column("pay_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_bindings", postgresql.JSONB(), nullable=False),
        sa.Column("policy_reference", postgresql.JSONB(), nullable=False),
        sa.Column("authority_references", postgresql.JSONB(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("replay_identity", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "run_id"], ["payroll_runs.company_id", "payroll_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "run_id", "snapshot_version", name="uq_payroll_calc_snapshot_run_version"),
        sa.UniqueConstraint("company_id", "input_digest", name="uq_payroll_calc_snapshot_digest"),
        sa.CheckConstraint("snapshot_version >= 1", name="ck_payroll_calc_snapshot_version"),
    )


def downgrade() -> None:
    op.drop_table("payroll_calculation_input_snapshots")
