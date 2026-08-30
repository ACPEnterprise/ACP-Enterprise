"""protect durable Procurement Match quantity and amount truth

Revision ID: g5e4c93b0f6d
Revises: f4d3b82a9e5c
"""

from collections.abc import Sequence

from alembic import op

revision: str = "g5e4c93b0f6d"
down_revision: str | Sequence[str] | None = "f4d3b82a9e5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_procurement_match_line_quantities",
        "procurement_three_way_match_lines",
        "ordered_quantity > 0 AND received_quantity >= 0 "
        "AND returned_quantity >= 0 AND returned_quantity <= received_quantity "
        "AND billed_quantity > 0",
    )
    op.create_check_constraint(
        "ck_procurement_match_line_net_accepted",
        "procurement_three_way_match_lines",
        "net_accepted_quantity = received_quantity - returned_quantity",
    )
    op.create_check_constraint(
        "ck_procurement_match_line_amounts",
        "procurement_three_way_match_lines",
        "po_unit_cost >= 0 AND billed_unit_cost >= 0 "
        "AND billed_net_amount >= 0 AND billed_tax_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_procurement_match_line_amounts",
        "procurement_three_way_match_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_procurement_match_line_net_accepted",
        "procurement_three_way_match_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_procurement_match_line_quantities",
        "procurement_three_way_match_lines",
        type_="check",
    )
