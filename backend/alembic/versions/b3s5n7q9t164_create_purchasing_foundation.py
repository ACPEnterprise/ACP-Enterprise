"""create operational purchasing foundation

Revision ID: b3s5n7q9t164
Revises: a2r4m6p8s053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b3s5n7q9t164"
down_revision: str | Sequence[str] | None = "a2r4m6p8s053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchasing_operational_vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("legal_name", sa.String(240)),
        sa.Column("contact_reference", sa.String(240)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provenance_type", sa.String(40), nullable=False),
        sa.Column("provenance_reference", sa.String(200)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','inactive','archived')",
            name="ck_purchasing_vendors_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_purchasing_vendors_version"),
        sa.UniqueConstraint("company_id", "code", name="uq_purchasing_vendor_code"),
        sa.UniqueConstraint("company_id", "id", name="uq_purchasing_vendor_company"),
    )
    op.create_index(
        "ix_purchasing_vendor_search",
        "purchasing_operational_vendors",
        ["company_id", "status", "display_name"],
    )
    op.create_table(
        "purchasing_purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("expected_date", sa.Date()),
        sa.Column(
            "prepared_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "issued_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column(
            "closed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("lifecycle_reason", sa.String(500)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_po_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "vendor_id"],
            [
                "purchasing_operational_vendors.company_id",
                "purchasing_operational_vendors.id",
            ],
            name="fk_purchasing_po_vendor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('draft','submitted','approved','issued','cancelled','closed')",
            name="ck_purchasing_po_status",
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_purchasing_po_currency"),
        sa.CheckConstraint("version >= 1", name="ck_purchasing_po_version"),
        sa.UniqueConstraint("company_id", "po_number", name="uq_purchasing_po_number"),
        sa.UniqueConstraint("company_id", "id", name="uq_purchasing_po_company"),
    )
    op.create_index(
        "ix_purchasing_po_list",
        "purchasing_purchase_orders",
        ["company_id", "branch_id", "status", "created_at"],
    )
    op.create_table(
        "purchasing_purchase_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("extended_cost", sa.Numeric(22, 4), nullable=False),
        sa.Column("expected_date", sa.Date()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_line_po",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "inventory_item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_purchasing_line_inventory_item",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_purchasing_line_quantity"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_purchasing_line_unit_cost"),
        sa.CheckConstraint(
            "extended_cost = quantity * unit_cost", name="ck_purchasing_line_extended"
        ),
        sa.CheckConstraint(
            "inventory_item_id IS NOT NULL OR length(trim(description)) > 0",
            name="ck_purchasing_line_identity",
        ),
        sa.CheckConstraint("version >= 1", name="ck_purchasing_line_version"),
        sa.UniqueConstraint(
            "company_id",
            "purchase_order_id",
            "line_number",
            name="uq_purchasing_line_number",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_purchasing_line_company"),
    )
    op.create_table(
        "purchasing_po_issuance_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_version", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "issued_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "purchase_order_id"],
            ["purchasing_purchase_orders.company_id", "purchasing_purchase_orders.id"],
            name="fk_purchasing_evidence_po",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "purchase_order_id", name="uq_purchasing_evidence_po"
        ),
        sa.UniqueConstraint(
            "company_id", "digest", name="uq_purchasing_evidence_digest"
        ),
    )
    op.create_table(
        "purchasing_command_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("result_type", sa.String(40), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_command_key"
        ),
        sa.CheckConstraint(
            "length(payload_digest) = 64", name="ck_purchasing_command_digest"
        ),
    )
    op.execute(
        "CREATE FUNCTION purchasing_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Purchasing issuance evidence is immutable'; END; $$"
    )
    op.execute(
        "CREATE TRIGGER trg_purchasing_evidence_immutable BEFORE UPDATE OR DELETE ON purchasing_po_issuance_evidence FOR EACH ROW EXECUTE FUNCTION purchasing_evidence_immutable()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_purchasing_evidence_immutable ON purchasing_po_issuance_evidence"
    )
    op.execute("DROP FUNCTION IF EXISTS purchasing_evidence_immutable()")
    op.drop_table("purchasing_command_receipts")
    op.drop_table("purchasing_po_issuance_evidence")
    op.drop_table("purchasing_purchase_order_lines")
    op.drop_index("ix_purchasing_po_list", table_name="purchasing_purchase_orders")
    op.drop_table("purchasing_purchase_orders")
    op.drop_index(
        "ix_purchasing_vendor_search", table_name="purchasing_operational_vendors"
    )
    op.drop_table("purchasing_operational_vendors")
