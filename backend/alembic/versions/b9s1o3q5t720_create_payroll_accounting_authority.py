"""create Payroll Accounting policy and mapping authority

Revision ID: b9s1o3q5t720
Revises: a8r0n2p4s619
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b9s1o3q5t720"
down_revision: str | Sequence[str] | None = "a8r0n2p4s619"
branch_labels = None
depends_on = None


def upgrade() -> None:
    events = "'payroll_accrual','payment_release','wage_settlement','tax_remittance','deduction_remittance','return_adjustment'"
    lifecycle = "'draft','approved','superseded','retired'"
    op.create_table(
        "payroll_accounting_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("policy_version", sa.Integer(), nullable=False), sa.Column("definition_version", sa.String(80), nullable=False), sa.Column("recognition_event", sa.String(32), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("effective_start", sa.Date(), nullable=False), sa.Column("effective_end", sa.Date()), sa.Column("lifecycle", sa.String(16), nullable=False), sa.Column("decision_evidence_digest", sa.String(64), nullable=False), sa.Column("policy_digest", sa.String(64), nullable=False), sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("supersedes_policy_id", postgresql.UUID(as_uuid=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"recognition_event IN ({events})", name="ck_payroll_accounting_policy_event"), sa.CheckConstraint(f"lifecycle IN ({lifecycle})", name="ck_payroll_accounting_policy_lifecycle"), sa.CheckConstraint("effective_end IS NULL OR effective_end > effective_start", name="ck_payroll_accounting_policy_interval"), sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supersedes_policy_id"], ["payroll_accounting_policy_versions.id"], ondelete="RESTRICT"), sa.UniqueConstraint("company_id", "recognition_event", "policy_version", name="uq_payroll_accounting_policy_version"), sa.UniqueConstraint("policy_digest"), sa.UniqueConstraint("supersedes_policy_id"),
    )
    op.create_index("ix_payroll_accounting_policy_resolution", "payroll_accounting_policy_versions", ["company_id", "recognition_event", "lifecycle", "effective_start", "effective_end"])
    op.create_table(
        "payroll_accounting_mapping_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("mapping_version", sa.Integer(), nullable=False), sa.Column("definition_version", sa.String(80), nullable=False), sa.Column("recognition_event", sa.String(32), nullable=False), sa.Column("component", sa.String(48), nullable=False), sa.Column("posting_side", sa.String(8), nullable=False), sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("effective_start", sa.Date(), nullable=False), sa.Column("effective_end", sa.Date()), sa.Column("lifecycle", sa.String(16), nullable=False), sa.Column("approval_evidence_digest", sa.String(64), nullable=False), sa.Column("mapping_digest", sa.String(64), nullable=False), sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("supersedes_mapping_id", postgresql.UUID(as_uuid=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"recognition_event IN ({events})", name="ck_payroll_accounting_mapping_event"), sa.CheckConstraint("posting_side IN ('debit','credit')", name="ck_payroll_accounting_mapping_side"), sa.CheckConstraint(f"lifecycle IN ({lifecycle})", name="ck_payroll_accounting_mapping_lifecycle"), sa.CheckConstraint("effective_end IS NULL OR effective_end > effective_start", name="ck_payroll_accounting_mapping_interval"), sa.ForeignKeyConstraint(["company_id", "account_id"], ["accounting_accounts.company_id", "accounting_accounts.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supersedes_mapping_id"], ["payroll_accounting_mapping_versions.id"], ondelete="RESTRICT"), sa.UniqueConstraint("company_id", "recognition_event", "component", "mapping_version", name="uq_payroll_accounting_mapping_version"), sa.UniqueConstraint("mapping_digest"), sa.UniqueConstraint("supersedes_mapping_id"),
    )
    op.create_index("ix_payroll_accounting_mapping_resolution", "payroll_accounting_mapping_versions", ["company_id", "recognition_event", "component", "lifecycle", "effective_start", "effective_end"])


def downgrade() -> None:
    op.drop_index("ix_payroll_accounting_mapping_resolution", table_name="payroll_accounting_mapping_versions")
    op.drop_table("payroll_accounting_mapping_versions")
    op.drop_index("ix_payroll_accounting_policy_resolution", table_name="payroll_accounting_policy_versions")
    op.drop_table("payroll_accounting_policy_versions")
