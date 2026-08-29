"""create replenishment decision evidence

Revision ID: v3m5i7k9n164
Revises: u2l4h6j8m053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "v3m5i7k9n164"
down_revision: str | Sequence[str] | None = "u2l4h6j8m053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchasing_replenishment_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_digest", sa.String(64), nullable=False),
        sa.Column("recommendation_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("approval_evidence_digest", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(18, 6)),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_purchasing_replenishment_decision",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_replenishment_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "vendor_id"],
            [
                "purchasing_operational_vendors.company_id",
                "purchasing_operational_vendors.id",
            ],
            name="fk_purchasing_replenishment_vendor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_replenishment_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_replenishment_po",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_replenishment_key"
        ),
        sa.UniqueConstraint(
            "company_id",
            "recommendation_digest",
            name="uq_purchasing_replenishment_recommendation",
        ),
    )


def downgrade() -> None:
    op.drop_table("purchasing_replenishment_decisions")
