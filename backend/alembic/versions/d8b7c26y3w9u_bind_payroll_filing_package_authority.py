"""Bind Payroll filing packages to tenant reporting authority.

Revision ID: d8b7c26y3w9u
Revises: c7a6b15x2v8t
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d8b7c26y3w9u"
down_revision: str | Sequence[str] | None = "c7a6b15x2v8t"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_payroll_reporting_company_id", "payroll_reporting_snapshots", ["company_id", "id"])
    op.create_unique_constraint("uq_payroll_compliance_schema_company_id", "payroll_compliance_schemas", ["company_id", "id"])
    op.create_unique_constraint("uq_payroll_filing_package_company_id", "payroll_filing_packages", ["company_id", "id"])
    for old_name in (
        "payroll_filing_packages_reporting_snapshot_id_fkey",
        "fk_payroll_filing_package_compliance_schema",
        "fk_payroll_filing_package_predecessor",
    ):
        op.drop_constraint(old_name, "payroll_filing_packages", type_="foreignkey")
    for name, parent, column in (
        ("fk_payroll_filing_package_reporting_scope", "payroll_reporting_snapshots", "reporting_snapshot_id"),
        ("fk_payroll_filing_package_schema_scope", "payroll_compliance_schemas", "compliance_schema_id"),
        ("fk_payroll_filing_package_predecessor_scope", "payroll_filing_packages", "supersedes_package_id"),
    ):
        op.create_foreign_key(name, "payroll_filing_packages", parent, ["company_id", column], ["company_id", "id"], ondelete="RESTRICT")


def downgrade() -> None:
    for name in (
        "fk_payroll_filing_package_predecessor_scope",
        "fk_payroll_filing_package_schema_scope",
        "fk_payroll_filing_package_reporting_scope",
    ):
        op.drop_constraint(name, "payroll_filing_packages", type_="foreignkey")
    for name, parent, column in (
        ("payroll_filing_packages_reporting_snapshot_id_fkey", "payroll_reporting_snapshots", "reporting_snapshot_id"),
        ("fk_payroll_filing_package_compliance_schema", "payroll_compliance_schemas", "compliance_schema_id"),
        ("fk_payroll_filing_package_predecessor", "payroll_filing_packages", "supersedes_package_id"),
    ):
        op.create_foreign_key(name, "payroll_filing_packages", parent, [column], ["id"], ondelete="RESTRICT")
    op.drop_constraint("uq_payroll_filing_package_company_id", "payroll_filing_packages", type_="unique")
    op.drop_constraint("uq_payroll_compliance_schema_company_id", "payroll_compliance_schemas", type_="unique")
    op.drop_constraint("uq_payroll_reporting_company_id", "payroll_reporting_snapshots", type_="unique")
