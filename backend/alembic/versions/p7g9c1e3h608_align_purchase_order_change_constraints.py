"""align purchase order change constraint names

Revision ID: p7g9c1e3h608
Revises: o6f8b0d2g497
"""

from collections.abc import Sequence

from alembic import op

revision: str = "p7g9c1e3h608"
down_revision: str | Sequence[str] | None = "o6f8b0d2g497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE purchasing_po_change_orders "
        "RENAME CONSTRAINT "
        "purchasing_po_change_orders_company_id_change_identity_key "
        "TO uq_purchasing_change_identity"
    )
    op.execute(
        "ALTER TABLE purchasing_po_change_orders "
        "RENAME CONSTRAINT purchasing_po_change_orders_company_id_id_key "
        "TO uq_purchasing_change_company"
    )
    op.execute(
        "ALTER TABLE purchasing_po_change_orders "
        "RENAME CONSTRAINT purchasing_po_change_orders_status_check "
        "TO ck_purchasing_change_status"
    )
    op.execute(
        "ALTER TABLE purchasing_po_revisions "
        "RENAME CONSTRAINT "
        "purchasing_po_revisions_company_id_purchase_order_id_revisi_key "
        "TO uq_purchasing_revision_number"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE purchasing_po_revisions "
        "RENAME CONSTRAINT uq_purchasing_revision_number "
        "TO purchasing_po_revisions_company_id_purchase_order_id_revisi_key"
    )
    op.execute(
        "ALTER TABLE purchasing_po_change_orders "
        "RENAME CONSTRAINT ck_purchasing_change_status "
        "TO purchasing_po_change_orders_status_check"
    )
    op.execute(
        "ALTER TABLE purchasing_po_change_orders "
        "RENAME CONSTRAINT uq_purchasing_change_company "
        "TO purchasing_po_change_orders_company_id_id_key"
    )
    op.execute(
        "ALTER TABLE purchasing_po_change_orders "
        "RENAME CONSTRAINT uq_purchasing_change_identity "
        "TO purchasing_po_change_orders_company_id_change_identity_key"
    )
