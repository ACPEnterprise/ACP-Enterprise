"""finalize Payroll Accounting posting authority

Revision ID: 12b7f12317d1
Revises: 11a6e01206c0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "12b7f12317d1"
down_revision: str | Sequence[str] | None = "11a6e01206c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_payroll_accounting_policy_event", "payroll_accounting_policy_versions", type_="check")
    op.create_check_constraint("ck_payroll_accounting_policy_event", "payroll_accounting_policy_versions", "recognition_event IN ('payroll_accrual','payment_release','wage_settlement','tax_remittance','deduction_remittance','return_adjustment','adjustment_applied')")
    op.drop_constraint("ck_payroll_accounting_mapping_event", "payroll_accounting_mapping_versions", type_="check")
    op.create_check_constraint("ck_payroll_accounting_mapping_event", "payroll_accounting_mapping_versions", "recognition_event IN ('payroll_accrual','payment_release','wage_settlement','tax_remittance','deduction_remittance','return_adjustment','adjustment_applied')")
    op.create_table(
        "payroll_accounting_consumptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("recognition_event", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("fact_digest", sa.String(64), nullable=False),
        sa.Column("candidate_identity", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("journal_id", sa.UUID(), nullable=True),
        sa.Column("journal_version", sa.Integer(), nullable=True),
        sa.Column("prepared_by_user_id", sa.UUID(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lifecycle IN ('prepared','posted','reconciliation_required','superseded','reversed')", name="ck_payroll_accounting_consumption_lifecycle"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_id"], ["accounting_journals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "candidate_identity", name="uq_payroll_accounting_consumption_identity"),
        sa.UniqueConstraint("company_id", "recognition_event", "source_event_id", name="uq_payroll_accounting_source_consumption"),
        sa.UniqueConstraint("company_id", "journal_id", name="uq_payroll_accounting_consumption_journal"),
    )
    op.create_index("ix_payroll_accounting_consumption_source", "payroll_accounting_consumptions", ["company_id", "source_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_payroll_accounting_consumption_source", table_name="payroll_accounting_consumptions")
    op.drop_table("payroll_accounting_consumptions")
    op.drop_constraint("ck_payroll_accounting_mapping_event", "payroll_accounting_mapping_versions", type_="check")
    op.create_check_constraint("ck_payroll_accounting_mapping_event", "payroll_accounting_mapping_versions", "recognition_event IN ('payroll_accrual','payment_release','wage_settlement','tax_remittance','deduction_remittance','return_adjustment')")
    op.drop_constraint("ck_payroll_accounting_policy_event", "payroll_accounting_policy_versions", type_="check")
    op.create_check_constraint("ck_payroll_accounting_policy_event", "payroll_accounting_policy_versions", "recognition_event IN ('payroll_accrual','payment_release','wage_settlement','tax_remittance','deduction_remittance','return_adjustment')")
