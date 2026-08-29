"""create Payroll tax/deduction result authority

Revision ID: x5o7k9m1p386
Revises: w4n6j8l0o275
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "x5o7k9m1p386"
down_revision: str | Sequence[str] | None = "w4n6j8l0o275"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_tax_deduction_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pay_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gross_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gross_calculation_digest", sa.String(64), nullable=False),
        sa.Column("result_identity", sa.String(96), nullable=False),
        sa.Column("calculation_version", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("admission_digest", sa.String(64), nullable=False),
        sa.Column("authority_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=False),
        sa.Column("gross_pay", sa.Numeric(18, 2), nullable=False),
        sa.Column("employee_tax_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("employee_deduction_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("employer_contribution_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_pay_candidate", sa.Numeric(18, 2), nullable=False),
        sa.Column("money_version", sa.String(80), nullable=False),
        sa.Column("calculation_digest", sa.String(64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lifecycle", sa.String(24), nullable=False),
        sa.Column("review_state", sa.String(24), nullable=False),
        sa.Column("supersedes_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lifecycle IN ('calculated','under_review','approved','rejected','superseded','voided')", name="ck_payroll_tax_result_lifecycle"),
        sa.CheckConstraint("review_state IN ('not_started','under_review','accepted','rejected')", name="ck_payroll_tax_result_review_state"),
        sa.ForeignKeyConstraint(["company_id", "gross_result_id"], ["payroll_gross_calculation_results.company_id", "payroll_gross_calculation_results.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_result_id"], ["payroll_tax_deduction_results.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_tax_result_company_id"),
        sa.UniqueConstraint("company_id", "result_identity", name="uq_payroll_tax_result_identity"),
        sa.UniqueConstraint("company_id", "calculation_digest", name="uq_payroll_tax_result_digest"),
        sa.UniqueConstraint("supersedes_result_id", name="uq_payroll_tax_result_successor"),
    )
    op.create_index("uq_payroll_tax_result_active_subject", "payroll_tax_deduction_results", ["company_id", "employee_id", "pay_period_id"], unique=True, postgresql_where=sa.text("lifecycle IN ('calculated','under_review','approved')"))
    op.create_index("ix_payroll_tax_result_period", "payroll_tax_deduction_results", ["company_id", "pay_period_id", "employee_id"])
    op.create_table(
        "payroll_tax_deduction_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_sequence", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("safe_note", sa.Text()),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('initiated','accepted','rejected')", name="ck_payroll_tax_review_decision"),
        sa.ForeignKeyConstraint(["company_id", "result_id"], ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("result_id", "review_sequence", name="uq_payroll_tax_review_sequence"),
        sa.UniqueConstraint("review_digest", name="uq_payroll_tax_review_digest"),
    )


def downgrade() -> None:
    op.drop_table("payroll_tax_deduction_reviews")
    op.drop_index("ix_payroll_tax_result_period", table_name="payroll_tax_deduction_results")
    op.drop_index("uq_payroll_tax_result_active_subject", table_name="payroll_tax_deduction_results")
    op.drop_table("payroll_tax_deduction_results")
