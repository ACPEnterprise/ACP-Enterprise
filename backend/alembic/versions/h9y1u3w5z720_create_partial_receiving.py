"""create partial receiving and discrepancy workflow

Revision ID: h9y1u3w5z720
Revises: g8x0t2v4y619
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "h9y1u3w5z720"
down_revision: str | Sequence[str] | None = "g8x0t2v4y619"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchasing_purchase_order_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receiving_event_identity", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("receiver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source_reference", sa.String(240)),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('recorded','discrepancy_outstanding')",
            name="ck_purchasing_receipt_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_receipt_po",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receiver_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id", "receiving_event_identity", name="uq_purchasing_receipt_event"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_purchasing_receipt_company"),
    )
    op.create_index(
        "ix_purchasing_receipt_po",
        "purchasing_purchase_order_receipts",
        ["company_id", "purchase_order_id", "received_at"],
    )
    op.create_table(
        "purchasing_purchase_order_receipt_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purchase_order_line_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("ordered_quantity_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("rejected_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_accepted_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("outstanding_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_snapshot", sa.String(40), nullable=False),
        sa.Column("discrepancy_category", sa.String(40)),
        sa.Column("observed_condition", sa.Text()),
        sa.CheckConstraint("accepted_quantity >= 0", name="ck_receipt_line_accepted"),
        sa.CheckConstraint("rejected_quantity >= 0", name="ck_receipt_line_rejected"),
        sa.CheckConstraint(
            "accepted_quantity + rejected_quantity > 0 OR discrepancy_category IS NOT NULL",
            name="ck_receipt_line_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            [
                "purchasing_purchase_order_receipts.company_id",
                "purchasing_purchase_order_receipts.id",
            ],
            name="fk_purchasing_receipt_line_receipt",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_line_id"],
            [
                "purchasing_purchase_order_lines.company_id",
                "purchasing_purchase_order_lines.id",
            ],
            name="fk_purchasing_receipt_line_po_line",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "receipt_id",
            "purchase_order_line_id",
            name="uq_purchasing_receipt_po_line",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_purchasing_receipt_line_company"
        ),
    )
    op.create_table(
        "purchasing_purchase_order_discrepancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purchase_order_line_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("expected_fact", sa.Text(), nullable=False),
        sa.Column("actual_fact", sa.Text(), nullable=False),
        sa.Column("observed_condition", sa.Text(), nullable=False),
        sa.Column("opened_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "category IN ('quantity_short','quantity_over','wrong_item','damaged_item','rejected_item','missing_line')",
            name="ck_purchasing_discrepancy_category",
        ),
        sa.CheckConstraint(
            "status IN ('open','resolved_accepted','resolved_rejected')",
            name="ck_purchasing_discrepancy_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_purchasing_discrepancy_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_id"],
            [
                "purchasing_purchase_order_receipts.company_id",
                "purchasing_purchase_order_receipts.id",
            ],
            name="fk_purchasing_discrepancy_receipt",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_line_id"],
            [
                "purchasing_purchase_order_receipt_lines.company_id",
                "purchasing_purchase_order_receipt_lines.id",
            ],
            name="fk_purchasing_discrepancy_receipt_line",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id", "receipt_line_id", name="uq_purchasing_discrepancy_line"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_purchasing_discrepancy_company"
        ),
    )
    op.create_index(
        "ix_purchasing_discrepancy_open",
        "purchasing_purchase_order_discrepancies",
        ["company_id", "purchase_order_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_purchasing_discrepancy_open",
        table_name="purchasing_purchase_order_discrepancies",
    )
    op.drop_table("purchasing_purchase_order_discrepancies")
    op.drop_table("purchasing_purchase_order_receipt_lines")
    op.drop_index(
        "ix_purchasing_receipt_po", table_name="purchasing_purchase_order_receipts"
    )
    op.drop_table("purchasing_purchase_order_receipts")
