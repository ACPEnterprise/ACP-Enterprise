"""create platform mutation receipts

Revision ID: d1t3p5r7v942
Revises: 14d9f34539f3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d1t3p5r7v942"
down_revision: str | Sequence[str] | None = "14d9f34539f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_mutation_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("result_type", sa.String(length=120), nullable=True),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("retention_class", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "retention_class IN ('transport', 'operational', 'financial_audit')",
            name="ck_platform_mutation_receipts_retention_class",
        ),
        sa.CheckConstraint(
            "state IN ('in_progress', 'completed', 'reconciliation_required')",
            name="ck_platform_mutation_receipts_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "operation",
            "idempotency_key",
            name="uq_platform_mutation_receipts_company_operation_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("platform_mutation_receipts")
