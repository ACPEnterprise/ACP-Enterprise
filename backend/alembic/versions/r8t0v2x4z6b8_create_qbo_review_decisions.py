"""create qbo review decisions

Revision ID: r8t0v2x4z6b8
Revises: rg7c9e1f3i5k7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r8t0v2x4z6b8"
down_revision: str | None = "rg7c9e1f3i5k7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_qbo_review_item_company",
        "qbo_native_review_items",
        ["company_id", "id"],
    )
    op.create_table(
        "qbo_native_review_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "application_record_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("authority_class", sa.String(length=32), nullable=False),
        sa.Column("target_native_type", sa.String(length=80), nullable=True),
        sa.Column("target_native_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.String(length=240), nullable=True),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "supersedes_decision_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action IN ('BIND_EXISTING','MAP_ACCOUNT','MAP_CUSTOMER','MAP_VENDOR',"
            "'CONFIRM_SOURCE_VERSION','HOLD_FOR_ACCOUNTANT','DEFER_EXTERNAL',"
            "'REJECT_WITH_REASON')",
            name="ck_qbo_review_decision_action",
        ),
        sa.CheckConstraint(
            "authority_class IN ('OWNER','ACCOUNTANT','EXTERNAL_EVIDENCE_REQUIRED')",
            name="ck_qbo_review_decision_authority",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "review_item_id"],
            ["qbo_native_review_items.company_id", "qbo_native_review_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["application_record_id"],
            ["qbo_native_application_records.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_decision_id"], ["qbo_native_review_decisions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "company_id", name="uq_qbo_review_decision_company"),
    )
    op.create_index(
        "uq_qbo_review_decision_current",
        "qbo_native_review_decisions",
        ["company_id", "review_item_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_qbo_review_decision_current", table_name="qbo_native_review_decisions"
    )
    op.drop_table("qbo_native_review_decisions")
    op.drop_constraint(
        "uq_qbo_review_item_company", "qbo_native_review_items", type_="unique"
    )
