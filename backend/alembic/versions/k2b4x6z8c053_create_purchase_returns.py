"""create purchase return workflow

Revision ID: k2b4x6z8c053
Revises: j1a3w5y7b942
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "k2b4x6z8c053"
down_revision: str | Sequence[str] | None = "j1a3w5y7b942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchasing_purchase_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purchase_order_line_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("return_identity", sa.String(128), nullable=False),
        sa.Column("item_identity_snapshot", sa.String(200), nullable=False),
        sa.Column("accepted_quantity_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("reason_note", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("authorization_status", sa.String(32), nullable=False),
        sa.Column("vendor_authorization_reference", sa.String(200)),
        sa.Column("vendor_instructions", sa.Text()),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorization_at", sa.DateTime(timezone=True)),
        sa.Column("returned_at", sa.DateTime(timezone=True)),
        sa.Column("vendor_received_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.Column("source_reference", sa.String(240)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_return_quantity"),
        sa.CheckConstraint(
            "reason IN ('damaged_after_receipt','defective','wrong_item','excess_not_needed','vendor_requested','other')",
            name="ck_purchase_return_reason",
        ),
        sa.CheckConstraint(
            "status IN ('requested','authorized','denied','return_ready','returned','received_by_vendor','closed','canceled')",
            name="ck_purchase_return_status",
        ),
        sa.CheckConstraint(
            "authorization_status IN ('not_requested','requested','received','denied','not_required')",
            name="ck_purchase_return_authorization",
        ),
        sa.CheckConstraint("version >= 1", name="ck_purchase_return_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchase_return_po",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            [
                "purchasing_purchase_order_receipts.company_id",
                "purchasing_purchase_order_receipts.id",
            ],
            name="fk_purchase_return_receipt",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_line_id"],
            [
                "purchasing_purchase_order_receipt_lines.company_id",
                "purchasing_purchase_order_receipt_lines.id",
            ],
            name="fk_purchase_return_receipt_line",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_line_id"],
            [
                "purchasing_purchase_order_lines.company_id",
                "purchasing_purchase_order_lines.id",
            ],
            name="fk_purchase_return_po_line",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id", "return_identity", name="uq_purchase_return_identity"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_purchase_return_company"),
    )
    op.create_index(
        "ix_purchase_return_po",
        "purchasing_purchase_returns",
        ["company_id", "purchase_order_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_return_po", table_name="purchasing_purchase_returns")
    op.drop_table("purchasing_purchase_returns")
