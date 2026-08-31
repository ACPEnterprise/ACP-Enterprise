"""Bind Payroll calculation successors to durable authority.

Revision ID: c7a6b15x2v8t
Revises: b6z5a04w1u7s
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7a6b15x2v8t"
down_revision: str | Sequence[str] | None = "b6z5a04w1u7s"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUCCESSORS = (
    (
        "payroll_gross_calculation_results",
        "payroll_gross_calculation_results_supersedes_result_id_fkey",
        "fk_payroll_gross_result_predecessor_scope",
        ["company_id", "employee_id", "pay_period_id", "supersedes_result_id"],
        ["company_id", "employee_id", "pay_period_id", "id"],
    ),
    (
        "payroll_tax_deduction_results",
        "payroll_tax_deduction_results_supersedes_result_id_fkey",
        "fk_payroll_tax_result_predecessor_scope",
        ["company_id", "employee_id", "pay_period_id", "supersedes_result_id"],
        ["company_id", "employee_id", "pay_period_id", "id"],
    ),
    (
        "payroll_adjustment_authorities",
        "payroll_adjustment_authorities_supersedes_adjustment_id_fkey",
        "fk_payroll_adjustment_predecessor_scope",
        ["company_id", "supersedes_adjustment_id"],
        ["company_id", "id"],
    ),
    (
        "payroll_adjustment_results",
        "payroll_adjustment_results_supersedes_result_id_fkey",
        "fk_payroll_adjustment_result_predecessor_scope",
        ["company_id", "supersedes_result_id"],
        ["company_id", "id"],
    ),
)


def upgrade() -> None:
    for table, old_name, new_name, local, remote in SUCCESSORS:
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(new_name, table, table, local, remote, ondelete="RESTRICT")


def downgrade() -> None:
    for table, old_name, new_name, local, _remote in reversed(SUCCESSORS):
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(
            old_name,
            table,
            table,
            [local[-1]],
            ["id"],
            ondelete="RESTRICT",
        )
