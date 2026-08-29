"""create Payroll gross result authority

Revision ID: u2l4h6j8m053
Revises: t1k3g5i7l942
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "u2l4h6j8m053"
down_revision: str | None = "t1k3g5i7l942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payroll_gross_calculation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pay_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("result_identity", sa.String(96), nullable=False),
        sa.Column("calculation_version", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_digest", sa.String(64), nullable=False),
        sa.Column(
            "compensation_authority_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("compensation_digest", sa.String(64), nullable=False),
        sa.Column("time_snapshot_id", sa.String(96)),
        sa.Column("time_snapshot_digest", sa.String(64)),
        sa.Column("admission_id", sa.String(96), nullable=False),
        sa.Column("admission_digest", sa.String(64), nullable=False),
        sa.Column("earning_components", postgresql.JSONB(), nullable=False),
        sa.Column("gross_pay_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("calculation_digest", sa.String(64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("lifecycle", sa.String(24), nullable=False),
        sa.Column("review_state", sa.String(24), nullable=False),
        sa.Column("supersedes_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lifecycle IN ('calculated','under_review','approved','superseded','voided')",
            name="ck_payroll_gross_result_lifecycle",
        ),
        sa.CheckConstraint(
            "review_state IN ('not_started','under_review','accepted','rejected')",
            name="ck_payroll_gross_result_review_state",
        ),
        sa.CheckConstraint(
            "gross_pay_total >= 0", name="ck_payroll_gross_total_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "policy_id"],
            [
                "payroll_company_policy_versions.company_id",
                "payroll_company_policy_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "compensation_authority_id"],
            [
                "payroll_compensation_authority_versions.company_id",
                "payroll_compensation_authority_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_result_id"],
            ["payroll_gross_calculation_results.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "calculation_digest",
            name="uq_payroll_gross_result_digest",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_gross_result_company_id"
        ),
        sa.UniqueConstraint(
            "company_id", "result_identity", name="uq_payroll_gross_result_identity"
        ),
        sa.UniqueConstraint(
            "supersedes_result_id", name="uq_payroll_gross_result_single_successor"
        ),
    )
    op.create_index(
        "uq_payroll_gross_result_active_subject_period",
        "payroll_gross_calculation_results",
        ["company_id", "employee_id", "pay_period_id"],
        unique=True,
        postgresql_where=sa.text(
            "lifecycle IN ('calculated','under_review','approved')"
        ),
    )
    op.create_index(
        "ix_payroll_gross_result_period",
        "payroll_gross_calculation_results",
        ["company_id", "pay_period_id", "lifecycle"],
    )
    op.create_table(
        "payroll_gross_calculation_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_sequence", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("safe_note", sa.Text()),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('initiated','accepted','rejected')",
            name="ck_payroll_gross_review_decision",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "result_id"],
            [
                "payroll_gross_calculation_results.company_id",
                "payroll_gross_calculation_results.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "result_id", "review_sequence", name="uq_payroll_gross_review_sequence"
        ),
    )
    op.create_index(
        "ix_payroll_gross_review_result",
        "payroll_gross_calculation_reviews",
        ["company_id", "result_id", "review_sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payroll_gross_review_result",
        table_name="payroll_gross_calculation_reviews",
    )
    op.drop_table("payroll_gross_calculation_reviews")
    op.drop_index(
        "ix_payroll_gross_result_period",
        table_name="payroll_gross_calculation_results",
    )
    op.drop_index(
        "uq_payroll_gross_result_active_subject_period",
        table_name="payroll_gross_calculation_results",
    )
    op.drop_table("payroll_gross_calculation_results")
