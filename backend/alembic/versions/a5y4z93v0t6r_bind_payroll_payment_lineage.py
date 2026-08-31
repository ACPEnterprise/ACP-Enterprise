"""Bind Payroll payment release, instruction, and execution lineage.

Revision ID: a5y4z93v0t6r
Revises: z4x3y82u9s5q
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a5y4z93v0t6r"
down_revision: str | Sequence[str] | None = "z4x3y82u9s5q"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, table, columns in (
        ("uq_payroll_tax_result_instruction_scope", "payroll_tax_deduction_results", ["company_id", "employee_id", "id"]),
        ("uq_payroll_payment_destination_instruction_scope", "payroll_payment_destination_versions", ["company_id", "employee_id", "id"]),
        ("uq_payroll_payment_release_execution_scope", "payroll_payment_releases", ["company_id", "payroll_run_id", "id"]),
        ("uq_payroll_payment_instruction_company_id", "payroll_payment_instructions", ["company_id", "id"]),
    ):
        op.create_unique_constraint(name, table, columns)

    op.drop_constraint("payroll_payment_destination_vers_supersedes_destination_id_fkey", "payroll_payment_destination_versions", type_="foreignkey")
    op.create_foreign_key(
        "fk_payroll_payment_destination_predecessor_scope",
        "payroll_payment_destination_versions",
        "payroll_payment_destination_versions",
        ["company_id", "employee_id", "supersedes_destination_id"],
        ["company_id", "employee_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("payroll_payment_releases_company_id_payroll_run_id_fkey", "payroll_payment_releases", type_="foreignkey")
    op.drop_constraint("payroll_payment_releases_supersedes_release_id_fkey", "payroll_payment_releases", type_="foreignkey")
    op.create_foreign_key(
        "fk_payroll_payment_release_run_scope", "payroll_payment_releases", "payroll_runs",
        ["company_id", "pay_period_id", "payroll_run_id"], ["company_id", "pay_period_id", "id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_payroll_payment_release_predecessor_scope", "payroll_payment_releases", "payroll_payment_releases",
        ["company_id", "payroll_run_id", "supersedes_release_id"], ["company_id", "payroll_run_id", "id"], ondelete="RESTRICT"
    )

    op.drop_constraint("payroll_payment_instructions_destination_id_fkey", "payroll_payment_instructions", type_="foreignkey")
    op.create_foreign_key(
        "fk_payroll_payment_instruction_tax_scope", "payroll_payment_instructions", "payroll_tax_deduction_results",
        ["company_id", "employee_id", "tax_result_id"], ["company_id", "employee_id", "id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_payroll_payment_instruction_destination_scope", "payroll_payment_instructions", "payroll_payment_destination_versions",
        ["company_id", "employee_id", "destination_id"], ["company_id", "employee_id", "id"], ondelete="RESTRICT"
    )

    op.drop_constraint("payroll_payment_executions_company_id_release_id_fkey", "payroll_payment_executions", type_="foreignkey")
    op.create_foreign_key(
        "fk_payroll_payment_execution_release_scope", "payroll_payment_executions", "payroll_payment_releases",
        ["company_id", "payroll_run_id", "release_id"], ["company_id", "payroll_run_id", "id"], ondelete="RESTRICT"
    )
    op.drop_constraint("payroll_payment_execution_items_instruction_id_fkey", "payroll_payment_execution_items", type_="foreignkey")
    op.create_foreign_key(
        "fk_payroll_payment_execution_item_instruction_scope", "payroll_payment_execution_items", "payroll_payment_instructions",
        ["company_id", "instruction_id"], ["company_id", "id"], ondelete="RESTRICT"
    )


def downgrade() -> None:
    op.drop_constraint("fk_payroll_payment_execution_item_instruction_scope", "payroll_payment_execution_items", type_="foreignkey")
    op.create_foreign_key("payroll_payment_execution_items_instruction_id_fkey", "payroll_payment_execution_items", "payroll_payment_instructions", ["instruction_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("fk_payroll_payment_execution_release_scope", "payroll_payment_executions", type_="foreignkey")
    op.create_foreign_key("payroll_payment_executions_company_id_release_id_fkey", "payroll_payment_executions", "payroll_payment_releases", ["company_id", "release_id"], ["company_id", "id"], ondelete="RESTRICT")

    op.drop_constraint("fk_payroll_payment_instruction_destination_scope", "payroll_payment_instructions", type_="foreignkey")
    op.drop_constraint("fk_payroll_payment_instruction_tax_scope", "payroll_payment_instructions", type_="foreignkey")
    op.create_foreign_key("payroll_payment_instructions_destination_id_fkey", "payroll_payment_instructions", "payroll_payment_destination_versions", ["destination_id"], ["id"], ondelete="RESTRICT")

    op.drop_constraint("fk_payroll_payment_release_predecessor_scope", "payroll_payment_releases", type_="foreignkey")
    op.drop_constraint("fk_payroll_payment_release_run_scope", "payroll_payment_releases", type_="foreignkey")
    op.create_foreign_key("payroll_payment_releases_supersedes_release_id_fkey", "payroll_payment_releases", "payroll_payment_releases", ["supersedes_release_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("payroll_payment_releases_company_id_payroll_run_id_fkey", "payroll_payment_releases", "payroll_runs", ["company_id", "payroll_run_id"], ["company_id", "id"], ondelete="RESTRICT")

    op.drop_constraint("fk_payroll_payment_destination_predecessor_scope", "payroll_payment_destination_versions", type_="foreignkey")
    op.create_foreign_key("payroll_payment_destination_vers_supersedes_destination_id_fkey", "payroll_payment_destination_versions", "payroll_payment_destination_versions", ["supersedes_destination_id"], ["id"], ondelete="RESTRICT")

    for name, table in (
        ("uq_payroll_payment_instruction_company_id", "payroll_payment_instructions"),
        ("uq_payroll_payment_release_execution_scope", "payroll_payment_releases"),
        ("uq_payroll_payment_destination_instruction_scope", "payroll_payment_destination_versions"),
        ("uq_payroll_tax_result_instruction_scope", "payroll_tax_deduction_results"),
    ):
        op.drop_constraint(name, table, type_="unique")
