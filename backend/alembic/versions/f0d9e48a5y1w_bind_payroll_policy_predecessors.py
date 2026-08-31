"""Bind Payroll policy and authority predecessors to Company.

Revision ID: f0d9e48a5y1w
Revises: d8b7c26y3w9u
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f0d9e48a5y1w"
down_revision: str | Sequence[str] | None = "d8b7c26y3w9u"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHAINS = (
    ("payroll_company_policy_versions", "payroll_company_policy_versions_supersedes_policy_id_fkey", "fk_payroll_company_policy_predecessor_scope", "supersedes_policy_id"),
    ("payroll_compensation_authority_versions", "payroll_compensation_authority_ver_supersedes_authority_id_fkey", "fk_payroll_compensation_predecessor_scope", "supersedes_authority_id"),
    ("payroll_input_authority_versions", "payroll_input_authority_versions_supersedes_authority_id_fkey", "fk_payroll_input_predecessor_scope", "supersedes_authority_id"),
    ("payroll_accounting_policy_versions", "payroll_accounting_policy_versions_supersedes_policy_id_fkey", "fk_payroll_accounting_policy_predecessor_scope", "supersedes_policy_id"),
    ("payroll_accounting_mapping_versions", "payroll_accounting_mapping_versions_supersedes_mapping_id_fkey", "fk_payroll_accounting_mapping_predecessor_scope", "supersedes_mapping_id"),
)


def upgrade() -> None:
    op.create_unique_constraint("uq_payroll_accounting_policy_company_id", "payroll_accounting_policy_versions", ["company_id", "id"])
    op.create_unique_constraint("uq_payroll_accounting_mapping_company_id", "payroll_accounting_mapping_versions", ["company_id", "id"])
    for table, old_name, new_name, column in CHAINS:
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(new_name, table, table, ["company_id", column], ["company_id", "id"], ondelete="RESTRICT")


def downgrade() -> None:
    for table, old_name, new_name, column in reversed(CHAINS):
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(old_name, table, table, [column], ["id"], ondelete="RESTRICT")
    op.drop_constraint("uq_payroll_accounting_mapping_company_id", "payroll_accounting_mapping_versions", type_="unique")
    op.drop_constraint("uq_payroll_accounting_policy_company_id", "payroll_accounting_policy_versions", type_="unique")
