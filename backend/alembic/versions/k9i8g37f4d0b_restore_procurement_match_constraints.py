"""Restore Procurement Match constraints after protected revision reconciliation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k9i8g37f4d0b"
down_revision: str | None = "j8h7f26e3c9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "procurement_three_way_match_lines"


def _constraint_exists(name: str) -> bool:
    return bool(
        op.get_bind().scalar(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_constraint "
                "WHERE conrelid = to_regclass(:table_name) AND conname = :name)"
            ),
            {"table_name": TABLE, "name": name},
        )
    )


def upgrade() -> None:
    if not _constraint_exists("ck_procurement_match_line_quantities"):
        op.create_check_constraint(
            "ck_procurement_match_line_quantities",
            TABLE,
            "ordered_quantity > 0 AND received_quantity >= 0 "
            "AND returned_quantity >= 0 AND returned_quantity <= received_quantity "
            "AND billed_quantity > 0",
        )
    if not _constraint_exists("ck_procurement_match_line_net_accepted"):
        op.create_check_constraint(
            "ck_procurement_match_line_net_accepted",
            TABLE,
            "net_accepted_quantity = received_quantity - returned_quantity",
        )
    if not _constraint_exists("ck_procurement_match_line_amounts"):
        op.create_check_constraint(
            "ck_procurement_match_line_amounts",
            TABLE,
            "po_unit_cost >= 0 AND billed_unit_cost >= 0 "
            "AND billed_net_amount >= 0 AND billed_tax_amount >= 0",
        )


def downgrade() -> None:
    op.drop_constraint(
        "ck_procurement_match_line_amounts", TABLE, type_="check"
    )
    op.drop_constraint(
        "ck_procurement_match_line_net_accepted", TABLE, type_="check"
    )
    op.drop_constraint(
        "ck_procurement_match_line_quantities", TABLE, type_="check"
    )
