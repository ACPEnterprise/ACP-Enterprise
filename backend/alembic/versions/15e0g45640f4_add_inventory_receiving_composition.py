"""add inventory receiving composition

Revision ID: 15e0g45640f4
Revises: d1t3p5r7v942
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "15e0g45640f4"
down_revision: str | Sequence[str] | None = "d1t3p5r7v942"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_inventory_movements_type", "inventory_stock_movements", type_="check"
    )
    op.drop_constraint(
        "ck_inventory_movements_locations",
        "inventory_stock_movements",
        type_="check",
    )
    op.create_check_constraint(
        "ck_inventory_movements_type",
        "inventory_stock_movements",
        "movement_type IN ('opening','increase','decrease','transfer','adjustment_in','adjustment_out','material_issue','material_issue_reversal','purchase_receipt','purchase_return')",
    )
    op.create_check_constraint(
        "ck_inventory_movements_locations",
        "inventory_stock_movements",
        "(movement_type = 'transfer' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type IN ('opening','increase','adjustment_in','material_issue_reversal','purchase_receipt') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR (movement_type IN ('decrease','adjustment_out','material_issue','purchase_return') AND source_location_id IS NOT NULL AND destination_location_id IS NULL)",
    )
    op.add_column(
        "purchasing_purchase_order_receipts",
        sa.Column("receiving_location_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "purchasing_purchase_order_receipts",
        sa.Column(
            "inventory_application_state",
            sa.String(length=24),
            server_default="pending",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_purchasing_receipt_inventory_application_state",
        "purchasing_purchase_order_receipts",
        "inventory_application_state IN ('pending','applied','not_applicable')",
    )
    op.create_foreign_key(
        "fk_purchasing_receipt_inventory_location",
        "purchasing_purchase_order_receipts",
        "inventory_stock_locations",
        ["company_id", "branch_id", "receiving_location_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "purchasing_purchase_order_receipts",
        "inventory_application_state",
        server_default=None,
    )
    op.add_column(
        "purchasing_purchase_order_receipt_lines",
        sa.Column("inventory_movement_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "purchasing_purchase_order_receipt_lines",
        sa.Column("unit_cost_snapshot", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "purchasing_purchase_order_receipt_lines",
        sa.Column("currency_snapshot", sa.String(length=3), nullable=True),
    )
    op.create_foreign_key(
        "fk_purchasing_receipt_line_inventory_movement",
        "purchasing_purchase_order_receipt_lines",
        "inventory_stock_movements",
        ["company_id", "inventory_movement_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "purchasing_purchase_returns",
        sa.Column("inventory_movement_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_purchase_return_inventory_movement",
        "purchasing_purchase_returns",
        "inventory_stock_movements",
        ["company_id", "inventory_movement_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_purchase_return_inventory_movement",
        "purchasing_purchase_returns",
        type_="foreignkey",
    )
    op.drop_column("purchasing_purchase_returns", "inventory_movement_id")
    op.drop_constraint(
        "fk_purchasing_receipt_line_inventory_movement",
        "purchasing_purchase_order_receipt_lines",
        type_="foreignkey",
    )
    op.drop_column("purchasing_purchase_order_receipt_lines", "currency_snapshot")
    op.drop_column("purchasing_purchase_order_receipt_lines", "unit_cost_snapshot")
    op.drop_column("purchasing_purchase_order_receipt_lines", "inventory_movement_id")
    op.drop_constraint(
        "fk_purchasing_receipt_inventory_location",
        "purchasing_purchase_order_receipts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_purchasing_receipt_inventory_application_state",
        "purchasing_purchase_order_receipts",
        type_="check",
    )
    op.drop_column("purchasing_purchase_order_receipts", "inventory_application_state")
    op.drop_column("purchasing_purchase_order_receipts", "receiving_location_id")
    op.drop_constraint(
        "ck_inventory_movements_locations",
        "inventory_stock_movements",
        type_="check",
    )
    op.drop_constraint(
        "ck_inventory_movements_type", "inventory_stock_movements", type_="check"
    )
    op.create_check_constraint(
        "ck_inventory_movements_type",
        "inventory_stock_movements",
        "movement_type IN ('opening','increase','decrease','transfer','adjustment_in','adjustment_out','material_issue','material_issue_reversal')",
    )
    op.create_check_constraint(
        "ck_inventory_movements_locations",
        "inventory_stock_movements",
        "(movement_type = 'transfer' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type IN ('opening','increase','adjustment_in','material_issue_reversal') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR (movement_type IN ('decrease','adjustment_out','material_issue') AND source_location_id IS NOT NULL AND destination_location_id IS NULL)",
    )
