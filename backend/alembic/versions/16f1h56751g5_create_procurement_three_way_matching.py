"""create procurement three way matching

Revision ID: 16f1h56751g5
Revises: 15e0g45640f4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "16f1h56751g5"
down_revision: str | Sequence[str] | None = "cb4c29cf0e3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ap_bill_lines_company_id", "ap_bill_lines", ["company_id", "id"]
    )
    op.create_table(
        "procurement_three_way_matches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("purchase_order_id", sa.UUID(), nullable=False),
        sa.Column("vendor_bill_id", sa.UUID(), nullable=False),
        sa.Column("operational_vendor_id", sa.UUID(), nullable=False),
        sa.Column("accounting_vendor_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("admission_state", sa.String(24), nullable=False),
        sa.Column("policy_reference", sa.String(160), nullable=True),
        sa.Column("purchase_order_version", sa.Integer(), nullable=False),
        sa.Column("bill_version", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("evaluated_by_user_id", sa.UUID(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "state IN ('matched','partially_matched','quantity_variance','price_variance','unreceived_billing','unbilled_receipt','overbilled','return_pending_credit','currency_conflict','vendor_conflict','item_conflict','blocked','requires_review')",
            name="ck_procurement_match_state",
        ),
        sa.CheckConstraint(
            "admission_state IN ('eligible','blocked','review_required')",
            name="ck_procurement_match_admission",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "vendor_bill_id"],
            ["ap_bills.company_id", "ap_bills.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "vendor_bill_id", name="uq_procurement_match_bill"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_procurement_match_company_id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_procurement_match_idempotency"
        ),
    )
    op.create_table(
        "procurement_three_way_match_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("purchase_order_line_id", sa.UUID(), nullable=False),
        sa.Column("receipt_line_id", sa.UUID(), nullable=True),
        sa.Column("bill_line_id", sa.UUID(), nullable=False),
        sa.Column("inventory_item_id", sa.UUID(), nullable=True),
        sa.Column("ordered_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("received_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("returned_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("net_accepted_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("billed_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("po_unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("billed_unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("billed_net_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("billed_tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("quantity_variance", sa.Numeric(18, 6), nullable=False),
        sa.Column("price_variance", sa.Numeric(18, 4), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "state IN ('matched','partially_matched','quantity_variance','price_variance','unreceived_billing','overbilled','return_pending_credit','item_conflict','blocked','requires_review')",
            name="ck_procurement_match_line_state",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "match_id"],
            [
                "procurement_three_way_matches.company_id",
                "procurement_three_way_matches.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_line_id"],
            [
                "purchasing_purchase_order_lines.company_id",
                "purchasing_purchase_order_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "bill_line_id"],
            ["ap_bill_lines.company_id", "ap_bill_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "receipt_line_id"],
            [
                "purchasing_purchase_order_receipt_lines.company_id",
                "purchasing_purchase_order_receipt_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "match_id",
            "bill_line_id",
            name="uq_procurement_match_line_bill",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_procurement_match_line_company_id"
        ),
    )
    op.create_table(
        "procurement_match_exceptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("match_line_id", sa.UUID(), nullable=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expected_evidence", sa.Text(), nullable=False),
        sa.Column("actual_evidence", sa.Text(), nullable=False),
        sa.Column("resolution", sa.String(40), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolution_idempotency_key", sa.String(128), nullable=True),
        sa.Column("resolution_payload_digest", sa.String(64), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open','reviewed','resolved')",
            name="ck_procurement_match_exception_status",
        ),
        sa.CheckConstraint(
            "category IN ('quantity_variance','price_variance','vendor_conflict','item_conflict','currency_conflict','missing_po','missing_receipt','missing_bill','duplicate_bill','duplicate_receipt','overbilled','return_pending_credit','damaged_or_short')",
            name="ck_procurement_match_exception_category",
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN ('accept_variance','request_vendor_credit','hold_bill','reject_bill','wait_for_receipt','wait_for_bill','correct_future_po','return_goods','manual_review_required')",
            name="ck_procurement_match_exception_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "match_id"],
            [
                "procurement_three_way_matches.company_id",
                "procurement_three_way_matches.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "match_line_id"],
            [
                "procurement_three_way_match_lines.company_id",
                "procurement_three_way_match_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "match_id",
            "category",
            "match_line_id",
            name="uq_procurement_match_exception_fact",
        ),
        sa.UniqueConstraint(
            "company_id",
            "resolution_idempotency_key",
            name="uq_procurement_match_resolution_idempotency",
        ),
    )


def downgrade() -> None:
    op.drop_table("procurement_match_exceptions")
    op.drop_table("procurement_three_way_match_lines")
    op.drop_table("procurement_three_way_matches")
    op.drop_constraint(
        "uq_ap_bill_lines_company_id", "ap_bill_lines", type_="unique"
    )
