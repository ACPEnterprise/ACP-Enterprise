"""Bind Payroll runs to tenant pay-period and predecessor authority.

Revision ID: y3w2x71t8r4p
Revises: x2v1w60s7q3o
"""

from collections.abc import Sequence

from alembic import op

revision: str = "y3w2x71t8r4p"
down_revision: str | Sequence[str] | None = "x2v1w60s7q3o"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "payroll_runs_pay_period_id_fkey", "payroll_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "payroll_runs_supersedes_run_id_fkey", "payroll_runs", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_payroll_runs_pay_period_scope",
        "payroll_runs",
        "timekeeping_pay_periods",
        ["company_id", "pay_period_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_payroll_runs_predecessor_scope",
        "payroll_runs",
        "payroll_runs",
        ["company_id", "supersedes_run_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payroll_runs_predecessor_scope", "payroll_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_payroll_runs_pay_period_scope", "payroll_runs", type_="foreignkey"
    )
    op.create_foreign_key(
        "payroll_runs_supersedes_run_id_fkey",
        "payroll_runs",
        "payroll_runs",
        ["supersedes_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "payroll_runs_pay_period_id_fkey",
        "payroll_runs",
        "timekeeping_pay_periods",
        ["pay_period_id"],
        ["id"],
        ondelete="RESTRICT",
    )
