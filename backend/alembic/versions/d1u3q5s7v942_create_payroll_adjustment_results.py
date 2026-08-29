"""create immutable Payroll adjustment result authority

Revision ID: d1u3q5s7v942
Revises: c0t2p4r6u831
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d1u3q5s7v942"
down_revision: str | None = "c0t2p4r6u831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payroll_adjustment_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("original_pay_period_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correction_pay_period_id", postgresql.UUID(as_uuid=True)),
        sa.Column("adjustment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adjustment_digest", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("classification", sa.String(48), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=False),
        sa.Column("consequences", postgresql.JSONB(), nullable=False),
        sa.Column("result_identity", sa.String(128), nullable=False),
        sa.Column("calculation_version", sa.String(80), nullable=False),
        sa.Column("calculation_digest", sa.String(64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lifecycle", sa.String(40), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("supersedes_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lifecycle IN ('calculated','under_review','approved','applied_to_successor_authority','rejected','superseded','voided')", name="ck_payroll_adjustment_result_lifecycle"),
        sa.ForeignKeyConstraint(["company_id", "adjustment_id"], ["payroll_adjustment_authorities.company_id", "payroll_adjustment_authorities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_result_id"], ["payroll_adjustment_results.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_adjustment_result_company_id"),
        sa.UniqueConstraint("company_id", "result_identity", name="uq_payroll_adjustment_result_identity"),
        sa.UniqueConstraint("company_id", "calculation_digest", name="uq_payroll_adjustment_result_digest"),
        sa.UniqueConstraint("supersedes_result_id", name="uq_payroll_adjustment_result_successor"),
    )
    op.create_index("uq_payroll_adjustment_result_active", "payroll_adjustment_results", ["company_id", "adjustment_id"], unique=True, postgresql_where=sa.text("lifecycle IN ('calculated','under_review','approved')"))
    op.create_table(
        "payroll_adjustment_result_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("safe_note", sa.Text()),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('initiated','accepted','rejected','approved')", name="ck_payroll_adjustment_result_review_decision"),
        sa.ForeignKeyConstraint(["company_id", "result_id"], ["payroll_adjustment_results.company_id", "payroll_adjustment_results.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("result_id", "sequence", name="uq_payroll_adjustment_result_review_sequence"),
        sa.UniqueConstraint("review_digest", name="uq_payroll_adjustment_result_review_digest"),
    )
    op.create_table(
        "payroll_adjustment_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("successor_authority_type", sa.String(80), nullable=False),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("authorized_components", postgresql.JSONB(), nullable=False),
        sa.Column("application_digest", sa.String(64), nullable=False),
        sa.Column("applied_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "result_id"], ["payroll_adjustment_results.company_id", "payroll_adjustment_results.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("result_id", "purpose", name="uq_payroll_adjustment_application_purpose"),
        sa.UniqueConstraint("application_digest", name="uq_payroll_adjustment_application_digest"),
    )


def downgrade() -> None:
    op.drop_table("payroll_adjustment_applications")
    op.drop_table("payroll_adjustment_result_reviews")
    op.drop_index("uq_payroll_adjustment_result_active", table_name="payroll_adjustment_results")
    op.drop_table("payroll_adjustment_results")
