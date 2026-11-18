"""Create encrypted Payroll blind-replay evidence.

Revision ID: ar1p3s5u7w9y
Revises: zq9s1u3w5y7a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ar1p3s5u7w9y"
down_revision: str | Sequence[str] | None = "zq9s1u3w5y7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payroll_shadow_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("calculation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(80), nullable=False),
        sa.Column("engine_sha", sa.String(40), nullable=False),
        sa.Column("tax_table_version", sa.String(120), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("frozen_before_qbo_reveal", sa.Boolean(), nullable=False),
        sa.Column("replay_identity", sa.String(200), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("snapshot_version >= 1", name="ck_payroll_shadow_version"),
        sa.CheckConstraint(
            "frozen_before_qbo_reveal", name="ck_payroll_shadow_frozen_before_qbo"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_shadow_company_id"),
        sa.UniqueConstraint(
            "company_id", "calculation_id", name="uq_payroll_shadow_calculation"
        ),
        sa.UniqueConstraint(
            "company_id", "replay_identity", name="uq_payroll_shadow_replay"
        ),
        sa.UniqueConstraint(
            "company_id",
            "input_digest",
            "snapshot_version",
            name="uq_payroll_shadow_input_version",
        ),
    )
    op.create_table(
        "payroll_qbo_answer_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_digest", sa.String(64), nullable=False),
        sa.Column("report_type", sa.String(120), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("answer_key_digest", sa.String(64), nullable=False),
        sa.Column(
            "imported_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "shadow_snapshot_id"],
            ["payroll_shadow_snapshots.company_id", "payroll_shadow_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_payroll_qbo_answer_company_id"
        ),
        sa.UniqueConstraint(
            "company_id", "source_file_digest", name="uq_payroll_qbo_answer_file"
        ),
    )
    op.create_table(
        "payroll_shadow_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "answer_key_record_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("comparison_digest", sa.String(64), nullable=False),
        sa.Column("unexplained_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "shadow_snapshot_id"],
            ["payroll_shadow_snapshots.company_id", "payroll_shadow_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "answer_key_record_id"],
            ["payroll_qbo_answer_keys.company_id", "payroll_qbo_answer_keys.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "shadow_snapshot_id",
            "answer_key_record_id",
            name="uq_payroll_shadow_comparison_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("payroll_shadow_comparisons")
    op.drop_table("payroll_qbo_answer_keys")
    op.drop_table("payroll_shadow_snapshots")
