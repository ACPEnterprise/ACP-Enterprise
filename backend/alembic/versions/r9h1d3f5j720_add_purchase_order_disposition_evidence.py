"""add purchase order disposition evidence

Revision ID: r9h1d3f5j720
Revises: q8h0d2f4i619
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "r9h1d3f5j720"
down_revision: str | Sequence[str] | None = "q8h0d2f4i619"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchasing_po_disposition_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_version", sa.Integer(), nullable=False),
        sa.Column("effective_revision", sa.Integer(), nullable=False),
        sa.Column("prior_status", sa.String(20), nullable=False),
        sa.Column("disposition", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("quantity_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "disposition IN ('fully_satisfied','canceled_before_receipt','remainder_canceled')"
        ),
        sa.UniqueConstraint(
            "company_id", "purchase_order_id", name="uq_purchasing_disposition_po"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_purchasing_disposition_company"
        ),
    )


def downgrade() -> None:
    op.drop_table("purchasing_po_disposition_evidence")
