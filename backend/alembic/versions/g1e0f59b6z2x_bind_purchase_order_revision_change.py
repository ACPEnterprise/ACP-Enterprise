"""Bind Purchase Order revisions to their exact change-order scope.

Revision ID: g1e0f59b6z2x
Revises: f0d9e48a5y1w
"""

from collections.abc import Sequence

from alembic import op

revision: str = "g1e0f59b6z2x"
down_revision: str | Sequence[str] | None = "f0d9e48a5y1w"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_purchasing_change_revision_scope",
        "purchasing_po_change_orders",
        ["company_id", "purchase_order_id", "id"],
    )
    op.drop_constraint(
        "purchasing_po_revisions_change_order_id_fkey",
        "purchasing_po_revisions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_purchasing_revision_change_scope",
        "purchasing_po_revisions",
        "purchasing_po_change_orders",
        ["company_id", "purchase_order_id", "change_order_id"],
        ["company_id", "purchase_order_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_purchasing_revision_change_scope",
        "purchasing_po_revisions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "purchasing_po_revisions_change_order_id_fkey",
        "purchasing_po_revisions",
        "purchasing_po_change_orders",
        ["change_order_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_purchasing_change_revision_scope",
        "purchasing_po_change_orders",
        type_="unique",
    )
