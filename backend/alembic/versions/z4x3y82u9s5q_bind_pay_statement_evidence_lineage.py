"""Bind Pay Statements to exact employee and period evidence lineage.

Revision ID: z4x3y82u9s5q
Revises: y3w2x71t8r4p
"""

from collections.abc import Sequence

from alembic import op

revision: str = "z4x3y82u9s5q"
down_revision: str | Sequence[str] | None = "y3w2x71t8r4p"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, table, columns in (
        ("uq_payroll_run_statement_scope", "payroll_runs", ["company_id", "pay_period_id", "id"]),
        ("uq_payroll_gross_result_statement_scope", "payroll_gross_calculation_results", ["company_id", "employee_id", "pay_period_id", "id"]),
        ("uq_payroll_tax_result_statement_scope", "payroll_tax_deduction_results", ["company_id", "employee_id", "pay_period_id", "id"]),
        ("uq_payroll_adjustment_result_statement_scope", "payroll_adjustment_results", ["company_id", "employee_id", "id"]),
        ("uq_payroll_reporting_statement_scope", "payroll_reporting_snapshots", ["company_id", "employee_id", "id"]),
        ("uq_payroll_pay_statement_predecessor_scope", "payroll_pay_statements", ["company_id", "employee_id", "pay_period_id", "id"]),
    ):
        op.create_unique_constraint(name, table, columns)

    op.drop_constraint(
        "payroll_tax_deduction_results_company_id_gross_result_id_fkey",
        "payroll_tax_deduction_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_payroll_tax_result_gross_scope",
        "payroll_tax_deduction_results",
        "payroll_gross_calculation_results",
        ["company_id", "employee_id", "pay_period_id", "gross_result_id"],
        ["company_id", "employee_id", "pay_period_id", "id"],
        ondelete="RESTRICT",
    )

    for old_name in (
        "payroll_pay_statements_company_id_run_id_fkey",
        "payroll_pay_statements_company_id_gross_result_id_fkey",
        "payroll_pay_statements_company_id_tax_result_id_fkey",
        "payroll_pay_statements_adjustment_result_id_fkey",
        "fk_payroll_pay_statements_reporting_snapshot",
        "payroll_pay_statements_supersedes_statement_id_fkey",
    ):
        op.drop_constraint(old_name, "payroll_pay_statements", type_="foreignkey")

    for name, parent, local, remote in (
        ("fk_payroll_pay_statement_run_scope", "payroll_runs", ["company_id", "pay_period_id", "run_id"], ["company_id", "pay_period_id", "id"]),
        ("fk_payroll_pay_statement_gross_scope", "payroll_gross_calculation_results", ["company_id", "employee_id", "pay_period_id", "gross_result_id"], ["company_id", "employee_id", "pay_period_id", "id"]),
        ("fk_payroll_pay_statement_tax_scope", "payroll_tax_deduction_results", ["company_id", "employee_id", "pay_period_id", "tax_result_id"], ["company_id", "employee_id", "pay_period_id", "id"]),
        ("fk_payroll_pay_statement_adjustment_scope", "payroll_adjustment_results", ["company_id", "employee_id", "adjustment_result_id"], ["company_id", "employee_id", "id"]),
        ("fk_payroll_pay_statement_reporting_scope", "payroll_reporting_snapshots", ["company_id", "employee_id", "reporting_snapshot_id"], ["company_id", "employee_id", "id"]),
        ("fk_payroll_pay_statement_predecessor_scope", "payroll_pay_statements", ["company_id", "employee_id", "pay_period_id", "supersedes_statement_id"], ["company_id", "employee_id", "pay_period_id", "id"]),
    ):
        op.create_foreign_key(name, "payroll_pay_statements", parent, local, remote, ondelete="RESTRICT")


def downgrade() -> None:
    for name in (
        "fk_payroll_pay_statement_predecessor_scope",
        "fk_payroll_pay_statement_reporting_scope",
        "fk_payroll_pay_statement_adjustment_scope",
        "fk_payroll_pay_statement_tax_scope",
        "fk_payroll_pay_statement_gross_scope",
        "fk_payroll_pay_statement_run_scope",
    ):
        op.drop_constraint(name, "payroll_pay_statements", type_="foreignkey")

    for name, parent, local, remote in (
        ("payroll_pay_statements_company_id_run_id_fkey", "payroll_runs", ["company_id", "run_id"], ["company_id", "id"]),
        ("payroll_pay_statements_company_id_gross_result_id_fkey", "payroll_gross_calculation_results", ["company_id", "gross_result_id"], ["company_id", "id"]),
        ("payroll_pay_statements_company_id_tax_result_id_fkey", "payroll_tax_deduction_results", ["company_id", "tax_result_id"], ["company_id", "id"]),
        ("payroll_pay_statements_adjustment_result_id_fkey", "payroll_adjustment_results", ["adjustment_result_id"], ["id"]),
        ("fk_payroll_pay_statements_reporting_snapshot", "payroll_reporting_snapshots", ["reporting_snapshot_id"], ["id"]),
        ("payroll_pay_statements_supersedes_statement_id_fkey", "payroll_pay_statements", ["supersedes_statement_id"], ["id"]),
    ):
        op.create_foreign_key(name, "payroll_pay_statements", parent, local, remote, ondelete="RESTRICT")

    op.drop_constraint("fk_payroll_tax_result_gross_scope", "payroll_tax_deduction_results", type_="foreignkey")
    op.create_foreign_key(
        "payroll_tax_deduction_results_company_id_gross_result_id_fkey",
        "payroll_tax_deduction_results",
        "payroll_gross_calculation_results",
        ["company_id", "gross_result_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    for name, table in (
        ("uq_payroll_pay_statement_predecessor_scope", "payroll_pay_statements"),
        ("uq_payroll_reporting_statement_scope", "payroll_reporting_snapshots"),
        ("uq_payroll_adjustment_result_statement_scope", "payroll_adjustment_results"),
        ("uq_payroll_tax_result_statement_scope", "payroll_tax_deduction_results"),
        ("uq_payroll_gross_result_statement_scope", "payroll_gross_calculation_results"),
        ("uq_payroll_run_statement_scope", "payroll_runs"),
    ):
        op.drop_constraint(name, table, type_="unique")
