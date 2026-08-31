"""Bind Payroll remittance and Accounting consumption lineage.

Revision ID: b6z5a04w1u7s
Revises: a5y4z93v0t6r
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b6z5a04w1u7s"
down_revision: str | Sequence[str] | None = "a5y4z93v0t6r"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_payroll_remittance_policy_company_id", "payroll_remittance_policies", ["company_id", "id"])
    op.create_unique_constraint("uq_payroll_remittance_destination_company_id", "payroll_remittance_destinations", ["company_id", "id"])
    op.create_unique_constraint(
        "uq_payroll_remittance_obligation_predecessor_scope",
        "payroll_remittance_obligations",
        ["company_id", "payroll_run_id", "classification", "id"],
    )

    for old_name in (
        "payroll_remittance_obligations_company_id_payroll_run_id_fkey",
        "payroll_remittance_obligations_policy_id_fkey",
        "payroll_remittance_obligations_destination_id_fkey",
        "payroll_remittance_obligations_supersedes_obligation_id_fkey",
    ):
        op.drop_constraint(old_name, "payroll_remittance_obligations", type_="foreignkey")

    for name, parent, local, remote in (
        ("fk_payroll_remittance_obligation_run_scope", "payroll_runs", ["company_id", "pay_period_id", "payroll_run_id"], ["company_id", "pay_period_id", "id"]),
        ("fk_payroll_remittance_obligation_policy_scope", "payroll_remittance_policies", ["company_id", "policy_id"], ["company_id", "id"]),
        ("fk_payroll_remittance_obligation_destination_scope", "payroll_remittance_destinations", ["company_id", "destination_id"], ["company_id", "id"]),
        ("fk_payroll_remittance_obligation_predecessor_scope", "payroll_remittance_obligations", ["company_id", "payroll_run_id", "classification", "supersedes_obligation_id"], ["company_id", "payroll_run_id", "classification", "id"]),
    ):
        op.create_foreign_key(name, "payroll_remittance_obligations", parent, local, remote, ondelete="RESTRICT")

    op.drop_constraint("payroll_remittance_instructions_destination_id_fkey", "payroll_remittance_instructions", type_="foreignkey")
    op.create_foreign_key(
        "fk_payroll_remittance_instruction_destination_scope",
        "payroll_remittance_instructions",
        "payroll_remittance_destinations",
        ["company_id", "destination_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("payroll_accounting_consumptions_journal_id_fkey", "payroll_accounting_consumptions", type_="foreignkey")
    op.create_foreign_key(
        "fk_payroll_accounting_consumption_journal_scope",
        "payroll_accounting_consumptions",
        "accounting_journals",
        ["company_id", "journal_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_payroll_accounting_consumption_journal_scope", "payroll_accounting_consumptions", type_="foreignkey")
    op.create_foreign_key("payroll_accounting_consumptions_journal_id_fkey", "payroll_accounting_consumptions", "accounting_journals", ["journal_id"], ["id"], ondelete="RESTRICT")

    op.drop_constraint("fk_payroll_remittance_instruction_destination_scope", "payroll_remittance_instructions", type_="foreignkey")
    op.create_foreign_key("payroll_remittance_instructions_destination_id_fkey", "payroll_remittance_instructions", "payroll_remittance_destinations", ["destination_id"], ["id"], ondelete="RESTRICT")

    for name in (
        "fk_payroll_remittance_obligation_predecessor_scope",
        "fk_payroll_remittance_obligation_destination_scope",
        "fk_payroll_remittance_obligation_policy_scope",
        "fk_payroll_remittance_obligation_run_scope",
    ):
        op.drop_constraint(name, "payroll_remittance_obligations", type_="foreignkey")
    for name, parent, local, remote in (
        ("payroll_remittance_obligations_company_id_payroll_run_id_fkey", "payroll_runs", ["company_id", "payroll_run_id"], ["company_id", "id"]),
        ("payroll_remittance_obligations_policy_id_fkey", "payroll_remittance_policies", ["policy_id"], ["id"]),
        ("payroll_remittance_obligations_destination_id_fkey", "payroll_remittance_destinations", ["destination_id"], ["id"]),
        ("payroll_remittance_obligations_supersedes_obligation_id_fkey", "payroll_remittance_obligations", ["supersedes_obligation_id"], ["id"]),
    ):
        op.create_foreign_key(name, "payroll_remittance_obligations", parent, local, remote, ondelete="RESTRICT")

    op.drop_constraint("uq_payroll_remittance_obligation_predecessor_scope", "payroll_remittance_obligations", type_="unique")
    op.drop_constraint("uq_payroll_remittance_destination_company_id", "payroll_remittance_destinations", type_="unique")
    op.drop_constraint("uq_payroll_remittance_policy_company_id", "payroll_remittance_policies", type_="unique")
