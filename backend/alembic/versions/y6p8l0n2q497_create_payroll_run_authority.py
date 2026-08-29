"""create Company pay-period Payroll run authority

Revision ID: y6p8l0n2q497
Revises: x5o7k9m1p386
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "y6p8l0n2q497"
down_revision: str | Sequence[str] | None = "x5o7k9m1p386"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pay_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_definition_id", sa.String(120), nullable=False),
        sa.Column("schedule_version", sa.String(80), nullable=False),
        sa.Column("assembly_version", sa.String(80), nullable=False),
        sa.Column("population_identity", sa.String(120), nullable=False),
        sa.Column("population_digest", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("run_identity", sa.String(96), nullable=False),
        sa.Column("run_digest", sa.String(64), nullable=False),
        sa.Column("aggregate_gross", sa.Numeric(18, 2), nullable=False),
        sa.Column("aggregate_employee_taxes", sa.Numeric(18, 2), nullable=False),
        sa.Column("aggregate_employee_deductions", sa.Numeric(18, 2), nullable=False),
        sa.Column("aggregate_net_pay", sa.Numeric(18, 2), nullable=False),
        sa.Column("aggregate_employer_contributions", sa.Numeric(18, 2), nullable=False),
        sa.Column("assembled_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assembled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifecycle", sa.String(24), nullable=False),
        sa.Column("review_state", sa.String(24), nullable=False),
        sa.Column("supersedes_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("consumed_by_payment_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lifecycle IN ('assembled','under_review','reviewed','approved','rejected','superseded','voided')", name="ck_payroll_run_lifecycle"),
        sa.CheckConstraint("review_state IN ('not_started','under_review','accepted','rejected')", name="ck_payroll_run_review_state"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pay_period_id"], ["timekeeping_pay_periods.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assembled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_run_id"], ["payroll_runs.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_run_company_id"),
        sa.UniqueConstraint("company_id", "run_identity", name="uq_payroll_run_identity"),
        sa.UniqueConstraint("company_id", "run_digest", name="uq_payroll_run_digest"),
        sa.UniqueConstraint("supersedes_run_id", name="uq_payroll_run_successor"),
    )
    op.create_index("uq_payroll_run_active_period", "payroll_runs", ["company_id", "pay_period_id"], unique=True, postgresql_where=sa.text("lifecycle IN ('assembled','under_review','reviewed','approved')"))
    op.create_table(
        "payroll_run_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("disposition", sa.String(24), nullable=False),
        sa.Column("gross_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("gross_result_digest", sa.String(64)),
        sa.Column("tax_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("tax_result_digest", sa.String(64)),
        sa.Column("blocker_evidence_digest", sa.String(64)),
        sa.Column("disposition_authority_digest", sa.String(64)),
        sa.Column("membership_digest", sa.String(64), nullable=False),
        sa.CheckConstraint("disposition IN ('ready','blocked','excluded','not_applicable')", name="ck_payroll_run_member_disposition"),
        sa.ForeignKeyConstraint(["company_id", "run_id"], ["payroll_runs.company_id", "payroll_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "employee_id"], ["employees.company_id", "employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "gross_result_id"], ["payroll_gross_calculation_results.company_id", "payroll_gross_calculation_results.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "tax_result_id"], ["payroll_tax_deduction_results.company_id", "payroll_tax_deduction_results.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("run_id", "employee_id", name="uq_payroll_run_member_employee"),
    )
    op.create_table(
        "payroll_run_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_sequence", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("safe_note", sa.Text()),
        sa.Column("run_digest", sa.String(64), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('initiated','accepted','rejected','approved')", name="ck_payroll_run_review_decision"),
        sa.ForeignKeyConstraint(["company_id", "run_id"], ["payroll_runs.company_id", "payroll_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("run_id", "review_sequence", name="uq_payroll_run_review_sequence"),
        sa.UniqueConstraint("review_digest", name="uq_payroll_run_review_digest"),
    )


def downgrade() -> None:
    op.drop_table("payroll_run_reviews")
    op.drop_table("payroll_run_members")
    op.drop_index("uq_payroll_run_active_period", table_name="payroll_runs")
    op.drop_table("payroll_runs")
