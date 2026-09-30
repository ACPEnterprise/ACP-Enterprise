"""Common stock seed catalog and vendor purchase-cost evidence.

Revision ID: ti9k1m3o5q7s
Revises: sh8d0f2g4j6l8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ti9k1m3o5q7s"
down_revision: str | Sequence[str] | None = "sh8d0f2g4j6l8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_material_catalog_admissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("inventory_item_id", sa.UUID(), nullable=True),
        sa.Column("source_filename", sa.String(240), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("row_digest", sa.String(64), nullable=False),
        sa.Column("source_payload", postgresql.JSONB(), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=False),
        sa.Column("hold_reason", sa.String(120), nullable=True),
        sa.Column("opening_inventory_state", sa.String(48), nullable=False),
        sa.Column("admitted_by_user_id", sa.UUID(), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("disposition IN ('admitted','held')", name="ck_material_admissions_disposition"),
        sa.CheckConstraint("opening_inventory_state = 'not_historically_reconstructed'", name="ck_material_admissions_opening_state"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["admitted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "inventory_item_id"], ["inventory_items.company_id", "inventory_items.id"], name="fk_material_admissions_item", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "source_digest", "source_row_number", name="uq_material_admissions_source_row"),
    )
    op.create_index("ix_material_admissions_source", "inventory_material_catalog_admissions", ["company_id", "source_digest", "disposition"])
    op.create_table(
        "purchasing_vendor_item_cross_references",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("inventory_item_id", sa.UUID(), nullable=False),
        sa.Column("vendor_sku", sa.String(160), nullable=False),
        sa.Column("match_state", sa.String(20), nullable=False),
        sa.Column("certified_by_user_id", sa.UUID(), nullable=True),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("match_state IN ('certified','review')", name="ck_vendor_item_xref_match_state"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["certified_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "vendor_id"], ["purchasing_operational_vendors.company_id", "purchasing_operational_vendors.id"], name="fk_vendor_item_xref_vendor", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "inventory_item_id"], ["inventory_items.company_id", "inventory_items.id"], name="fk_vendor_item_xref_item", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_vendor_item_xref_company_id"),
        sa.UniqueConstraint("company_id", "vendor_id", "vendor_sku", name="uq_vendor_item_xref_vendor_sku"),
    )
    op.create_index("ix_vendor_item_xref_item", "purchasing_vendor_item_cross_references", ["company_id", "inventory_item_id", "vendor_id"])
    op.create_table(
        "purchasing_vendor_purchase_cost_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("vendor_item_cross_reference_id", sa.UUID(), nullable=False),
        sa.Column("purchase_cost", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("cost_basis", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purchase_cost >= 0", name="ck_vendor_cost_evidence_cost"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_vendor_cost_evidence_currency"),
        sa.CheckConstraint("cost_basis = 'vendor_purchase_before_delivery_and_tax'", name="ck_vendor_cost_evidence_basis"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "vendor_item_cross_reference_id"], ["purchasing_vendor_item_cross_references.company_id", "purchasing_vendor_item_cross_references.id"], name="fk_vendor_cost_evidence_xref", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "evidence_digest", name="uq_vendor_cost_evidence_digest"),
    )
    op.create_index("ix_vendor_cost_evidence_current", "purchasing_vendor_purchase_cost_evidence", ["company_id", "vendor_item_cross_reference_id", "observed_at"])
    op.execute("""
        CREATE FUNCTION reject_material_seed_evidence_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'material seed evidence is append-only'; END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("inventory_material_catalog_admissions", "purchasing_vendor_purchase_cost_evidence"):
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_material_seed_evidence_mutation()")


def downgrade() -> None:
    for table in ("purchasing_vendor_purchase_cost_evidence", "inventory_material_catalog_admissions"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_material_seed_evidence_mutation()")
    op.drop_index("ix_vendor_cost_evidence_current", table_name="purchasing_vendor_purchase_cost_evidence")
    op.drop_table("purchasing_vendor_purchase_cost_evidence")
    op.drop_index("ix_vendor_item_xref_item", table_name="purchasing_vendor_item_cross_references")
    op.drop_table("purchasing_vendor_item_cross_references")
    op.drop_index("ix_material_admissions_source", table_name="inventory_material_catalog_admissions")
    op.drop_table("inventory_material_catalog_admissions")
