"""create Payroll payment execution and settlement evidence authority

Revision ID: a8r0n2p4s619
Revises: z7q9m1o3r508
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a8r0n2p4s619"
down_revision: str | Sequence[str] | None = "z7q9m1o3r508"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_payment_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("payroll_run_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("package_digest", sa.String(64), nullable=False), sa.Column("definition_version", sa.String(80), nullable=False), sa.Column("provider_identity", sa.String(80), nullable=False), sa.Column("provider_version", sa.String(40), nullable=False), sa.Column("execution_idempotency_key", sa.String(96), nullable=False), sa.Column("execution_identity", sa.String(96), nullable=False), sa.Column("execution_digest", sa.String(64), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("authorized_total", sa.Numeric(18, 2), nullable=False), sa.Column("lifecycle", sa.String(32), nullable=False), sa.Column("authorized_by_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False), sa.Column("provider_reference", sa.String(120)), sa.Column("request_digest", sa.String(64)), sa.Column("response_digest", sa.String(64)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lifecycle IN ('authorized','submission_pending','submitted','provider_acknowledged','settlement_pending','partially_settled','settled','rejected','failed','canceled','uncertain')", name="ck_payroll_payment_execution_lifecycle"), sa.ForeignKeyConstraint(["company_id", "release_id"], ["payroll_payment_releases.company_id", "payroll_payment_releases.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.UniqueConstraint("company_id", "id", name="uq_payroll_payment_execution_company_id"), sa.UniqueConstraint("company_id", "execution_identity", name="uq_payroll_payment_execution_identity"), sa.UniqueConstraint("company_id", "execution_digest", name="uq_payroll_payment_execution_digest"),
    )
    op.create_index("uq_payroll_payment_execution_active_release", "payroll_payment_executions", ["company_id", "release_id"], unique=True, postgresql_where=sa.text("lifecycle IN ('authorized','submission_pending','submitted','provider_acknowledged','settlement_pending','partially_settled','uncertain')"))
    op.create_table(
        "payroll_payment_execution_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("instruction_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("instruction_digest", sa.String(64), nullable=False), sa.Column("amount", sa.Numeric(18, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("lifecycle", sa.String(24), nullable=False), sa.Column("provider_safe_reference", sa.String(120)), sa.Column("evidence_digest", sa.String(64)),
        sa.CheckConstraint("lifecycle IN ('authorized','submitted','acknowledged','settlement_pending','settled','rejected','failed','unresolved')", name="ck_payroll_payment_execution_item_lifecycle"), sa.ForeignKeyConstraint(["company_id", "execution_id"], ["payroll_payment_executions.company_id", "payroll_payment_executions.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["instruction_id"], ["payroll_payment_instructions.id"], ondelete="RESTRICT"), sa.UniqueConstraint("execution_id", "instruction_id", name="uq_payroll_payment_execution_item_instruction"),
    )
    op.create_table(
        "payroll_payment_execution_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("evidence_type", sa.String(24), nullable=False), sa.Column("provider_identity", sa.String(80), nullable=False), sa.Column("provider_version", sa.String(40), nullable=False), sa.Column("provider_safe_reference", sa.String(120)), sa.Column("request_digest", sa.String(64), nullable=False), sa.Column("response_digest", sa.String(64), nullable=False), sa.Column("evidence_digest", sa.String(64), nullable=False), sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("evidence_type IN ('submission','acknowledgement','settlement','failure','uncertain')", name="ck_payroll_payment_execution_evidence_type"), sa.ForeignKeyConstraint(["company_id", "execution_id"], ["payroll_payment_executions.company_id", "payroll_payment_executions.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.UniqueConstraint("execution_id", "evidence_digest", name="uq_payroll_payment_execution_evidence_digest"),
    )


def downgrade() -> None:
    op.drop_table("payroll_payment_execution_evidence")
    op.drop_table("payroll_payment_execution_items")
    op.drop_index("uq_payroll_payment_execution_active_release", table_name="payroll_payment_executions")
    op.drop_table("payroll_payment_executions")
