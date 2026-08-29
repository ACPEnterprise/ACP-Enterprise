"""create protected pay statement authority

Revision ID: 13c8f23428e2
Revises: 12b7f12317d1
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "13c8f23428e2"
down_revision: str | Sequence[str] | None = "12b7f12317d1"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("payroll_pay_statements",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("company_id", sa.UUID(), nullable=False), sa.Column("employee_id", sa.UUID(), nullable=False), sa.Column("pay_period_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False), sa.Column("run_digest", sa.String(64), nullable=False), sa.Column("gross_result_id", sa.UUID(), nullable=False), sa.Column("gross_result_digest", sa.String(64), nullable=False), sa.Column("tax_result_id", sa.UUID(), nullable=False), sa.Column("tax_result_digest", sa.String(64), nullable=False),
        sa.Column("adjustment_result_id", sa.UUID(), nullable=True), sa.Column("adjustment_digest", sa.String(64), nullable=True), sa.Column("statement_version", sa.Integer(), nullable=False), sa.Column("definition_version", sa.String(80), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("payment_status", sa.String(24), nullable=False), sa.Column("payment_evidence_digest", sa.String(64), nullable=True), sa.Column("content", postgresql.JSONB(), nullable=False), sa.Column("ytd_status", sa.String(24), nullable=False), sa.Column("statement_identity", sa.String(128), nullable=False), sa.Column("statement_digest", sa.String(64), nullable=False), sa.Column("lifecycle", sa.String(16), nullable=False), sa.Column("supersedes_statement_id", sa.UUID(), nullable=True), sa.Column("issued_by_user_id", sa.UUID(), nullable=True), sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_by_user_id", sa.UUID(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lifecycle IN ('created','issued','superseded','voided')", name="ck_payroll_pay_statement_lifecycle"), sa.CheckConstraint("payment_status IN ('not_available','pending','acknowledged','partially_settled','settled','failed','unresolved')", name="ck_payroll_pay_statement_payment_status"),
        sa.ForeignKeyConstraint(["company_id", "employee_id"], ["employees.company_id", "employees.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["company_id", "gross_result_id"], ["payroll_gross_calculation_results.company_id", "payroll_gross_calculation_results.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["company_id", "run_id"], ["payroll_runs.company_id", "payroll_runs.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["company_id", "tax_result_id"], ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["adjustment_result_id"], ["payroll_adjustment_results.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supersedes_statement_id"], ["payroll_pay_statements.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("company_id", "statement_identity", name="uq_payroll_pay_statement_identity"), sa.UniqueConstraint("company_id", "statement_digest", name="uq_payroll_pay_statement_digest"), sa.UniqueConstraint("supersedes_statement_id", name="uq_payroll_pay_statement_successor"))
    op.create_index("ix_payroll_pay_statement_employee_period", "payroll_pay_statements", ["company_id", "employee_id", "pay_period_id", "created_at"])

def downgrade() -> None:
    op.drop_index("ix_payroll_pay_statement_employee_period", table_name="payroll_pay_statements")
    op.drop_table("payroll_pay_statements")
