"""create protected Payroll payment release authority

Revision ID: z7q9m1o3r508
Revises: y6p8l0n2q497
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "z7q9m1o3r508"
down_revision: str | Sequence[str] | None = "y6p8l0n2q497"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_payment_destination_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_version", sa.Integer(), nullable=False), sa.Column("definition_version", sa.String(80), nullable=False), sa.Column("method_type", sa.String(32), nullable=False), sa.Column("destination_reference", sa.String(120), nullable=False), sa.Column("protected_envelope_id", postgresql.UUID(as_uuid=True)), sa.Column("masked_display", sa.String(80), nullable=False), sa.Column("verification_evidence_digest", sa.String(64), nullable=False), sa.Column("effective_start", sa.Date(), nullable=False), sa.Column("effective_end", sa.Date()), sa.Column("lifecycle", sa.String(20), nullable=False), sa.Column("authority_digest", sa.String(64), nullable=False), sa.Column("supersedes_destination_id", postgresql.UUID(as_uuid=True)), sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("audit_reason", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("method_type IN ('direct_deposit','paper_check','other')", name="ck_payroll_payment_destination_method"), sa.CheckConstraint("lifecycle IN ('draft','approved','superseded','revoked','expired')", name="ck_payroll_payment_destination_lifecycle"), sa.CheckConstraint("effective_end IS NULL OR effective_end > effective_start", name="ck_payroll_payment_destination_interval"),
        sa.ForeignKeyConstraint(["company_id", "employee_id"], ["employees.company_id", "employees.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["company_id", "protected_envelope_id"], ["payroll_protected_input_envelopes.company_id", "payroll_protected_input_envelopes.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supersedes_destination_id"], ["payroll_payment_destination_versions.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_payment_destination_company_id"), sa.UniqueConstraint("company_id", "employee_id", "destination_version", name="uq_payroll_payment_destination_version"),
    )
    op.create_index("ix_payroll_payment_destination_resolution", "payroll_payment_destination_versions", ["company_id", "employee_id", "lifecycle", "effective_start", "effective_end"])
    op.create_table(
        "payroll_payment_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("payroll_run_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("payroll_run_digest", sa.String(64), nullable=False), sa.Column("pay_period_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("definition_version", sa.String(80), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("package_identity", sa.String(96), nullable=False), sa.Column("package_digest", sa.String(64), nullable=False), sa.Column("aggregate_release_amount", sa.Numeric(18, 2), nullable=False), sa.Column("assembled_by_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("assembled_at", sa.DateTime(timezone=True), nullable=False), sa.Column("lifecycle", sa.String(28), nullable=False), sa.Column("review_state", sa.String(24), nullable=False), sa.Column("supersedes_release_id", postgresql.UUID(as_uuid=True)), sa.Column("execution_started_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lifecycle IN ('draft','under_review','approved_for_release','rejected','superseded','voided')", name="ck_payroll_payment_release_lifecycle"), sa.CheckConstraint("review_state IN ('not_started','under_review','accepted','rejected')", name="ck_payroll_payment_release_review_state"), sa.ForeignKeyConstraint(["company_id", "payroll_run_id"], ["payroll_runs.company_id", "payroll_runs.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["assembled_by_user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supersedes_release_id"], ["payroll_payment_releases.id"], ondelete="RESTRICT"), sa.UniqueConstraint("company_id", "id", name="uq_payroll_payment_release_company_id"), sa.UniqueConstraint("company_id", "package_identity", name="uq_payroll_payment_release_identity"), sa.UniqueConstraint("company_id", "package_digest", name="uq_payroll_payment_release_digest"), sa.UniqueConstraint("supersedes_release_id", name="uq_payroll_payment_release_successor"),
    )
    op.create_index("uq_payroll_payment_release_active_run", "payroll_payment_releases", ["company_id", "payroll_run_id"], unique=True, postgresql_where=sa.text("lifecycle IN ('draft','under_review','approved_for_release')"))
    op.create_table(
        "payroll_payment_instructions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("disposition", sa.String(24), nullable=False), sa.Column("run_member_digest", sa.String(64), nullable=False), sa.Column("tax_result_id", postgresql.UUID(as_uuid=True)), sa.Column("tax_result_digest", sa.String(64)), sa.Column("destination_id", postgresql.UUID(as_uuid=True)), sa.Column("destination_digest", sa.String(64)), sa.Column("method_type", sa.String(32)), sa.Column("protected_destination_reference", sa.String(120)), sa.Column("amount", sa.Numeric(18, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("blocker_evidence_digest", sa.String(64)), sa.Column("instruction_identity", sa.String(96), nullable=False), sa.Column("instruction_digest", sa.String(64), nullable=False),
        sa.CheckConstraint("disposition IN ('ready','blocked','excluded','not_applicable')", name="ck_payroll_payment_instruction_disposition"), sa.ForeignKeyConstraint(["company_id", "release_id"], ["payroll_payment_releases.company_id", "payroll_payment_releases.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["company_id", "employee_id"], ["employees.company_id", "employees.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["destination_id"], ["payroll_payment_destination_versions.id"], ondelete="RESTRICT"), sa.UniqueConstraint("release_id", "employee_id", name="uq_payroll_payment_instruction_employee"), sa.UniqueConstraint("company_id", "instruction_identity", name="uq_payroll_payment_instruction_identity"),
    )
    op.create_table(
        "payroll_payment_release_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("review_sequence", sa.Integer(), nullable=False), sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("decision", sa.String(20), nullable=False), sa.Column("reason_code", sa.String(80), nullable=False), sa.Column("safe_note", sa.Text()), sa.Column("package_digest", sa.String(64), nullable=False), sa.Column("review_digest", sa.String(64), nullable=False), sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('initiated','accepted','rejected','approved')", name="ck_payroll_payment_release_review_decision"), sa.ForeignKeyConstraint(["company_id", "release_id"], ["payroll_payment_releases.company_id", "payroll_payment_releases.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"), sa.UniqueConstraint("release_id", "review_sequence", name="uq_payroll_payment_release_review_sequence"), sa.UniqueConstraint("review_digest", name="uq_payroll_payment_release_review_digest"),
    )


def downgrade() -> None:
    op.drop_table("payroll_payment_release_reviews")
    op.drop_table("payroll_payment_instructions")
    op.drop_index("uq_payroll_payment_release_active_run", table_name="payroll_payment_releases")
    op.drop_table("payroll_payment_releases")
    op.drop_index("ix_payroll_payment_destination_resolution", table_name="payroll_payment_destination_versions")
    op.drop_table("payroll_payment_destination_versions")
