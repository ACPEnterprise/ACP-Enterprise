"""create append-only Payroll adjustment authority

Revision ID: c0t2p4r6u831
Revises: c0t2q4s6u831
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c0t2p4r6u831"
down_revision: str | Sequence[str] | None = "c0t2q4s6u831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_adjustment_authorities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("employee_id", postgresql.UUID(as_uuid=True)), sa.Column("original_pay_period_id", postgresql.UUID(as_uuid=True)), sa.Column("off_cycle_pay_period_id", postgresql.UUID(as_uuid=True)), sa.Column("classification", sa.String(48), nullable=False), sa.Column("reason_code", sa.String(80), nullable=False), sa.Column("source_type", sa.String(48), nullable=False), sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("source_digest", sa.String(64), nullable=False), sa.Column("source_evidence", postgresql.JSONB(), nullable=False), sa.Column("delta_components", postgresql.JSONB(), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("effective_date", sa.Date(), nullable=False), sa.Column("evidence_digest", sa.String(64), nullable=False), sa.Column("definition_version", sa.String(80), nullable=False), sa.Column("adjustment_identity", sa.String(96), nullable=False), sa.Column("adjustment_digest", sa.String(64), nullable=False), sa.Column("lifecycle", sa.String(36), nullable=False), sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("supersedes_adjustment_id", postgresql.UUID(as_uuid=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("classification IN ('pre_payment_payroll_correction','retroactive_earnings','off_cycle_payroll','tax_correction','deduction_correction','payment_return','payment_rejection','payment_reversal','settlement_correction','accounting_adjustment_required')", name="ck_payroll_adjustment_classification"), sa.CheckConstraint("lifecycle IN ('draft','under_review','approved','applied_to_successor_authority','rejected','superseded','voided')", name="ck_payroll_adjustment_lifecycle"), sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supersedes_adjustment_id"], ["payroll_adjustment_authorities.id"], ondelete="RESTRICT"), sa.UniqueConstraint("company_id", "id", name="uq_payroll_adjustment_company_id"), sa.UniqueConstraint("company_id", "adjustment_identity", name="uq_payroll_adjustment_identity"), sa.UniqueConstraint("company_id", "adjustment_digest", name="uq_payroll_adjustment_digest"), sa.UniqueConstraint("supersedes_adjustment_id", name="uq_payroll_adjustment_successor"),
    )
    op.create_index("uq_payroll_adjustment_active_subject", "payroll_adjustment_authorities", ["company_id", "source_type", "source_id", "classification"], unique=True, postgresql_where=sa.text("lifecycle IN ('draft','under_review','approved')"))
    op.create_table(
        "payroll_adjustment_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("adjustment_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("decision", sa.String(20), nullable=False), sa.Column("reason_code", sa.String(80), nullable=False), sa.Column("safe_note", sa.Text()), sa.Column("adjustment_digest", sa.String(64), nullable=False), sa.Column("review_digest", sa.String(64), nullable=False), sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('initiated','accepted','rejected','approved')", name="ck_payroll_adjustment_review_decision"), sa.ForeignKeyConstraint(["company_id", "adjustment_id"], ["payroll_adjustment_authorities.company_id", "payroll_adjustment_authorities.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"), sa.UniqueConstraint("adjustment_id", "sequence", name="uq_payroll_adjustment_review_sequence"), sa.UniqueConstraint("review_digest", name="uq_payroll_adjustment_review_digest"),
    )


def downgrade() -> None:
    op.drop_table("payroll_adjustment_reviews")
    op.drop_index("uq_payroll_adjustment_active_subject", table_name="payroll_adjustment_authorities")
    op.drop_table("payroll_adjustment_authorities")
