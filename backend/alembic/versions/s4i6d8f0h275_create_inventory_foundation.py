"""create inventory foundation

Revision ID: s4i6d8f0h275
Revises: s4i6d8e0a275
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "s4i6d8f0h275"
down_revision: str | None = "s4i6d8e0a275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def company_branch_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["company_id", "branch_id"],
        ["branches.company_id", "branches.id"],
        name=name,
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("stocking_unit", sa.String(40), nullable=False),
        sa.Column("allow_fractional", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_inventory_items_code",
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_inventory_items_name"),
        sa.CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_items_unit"
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','inactive','archived')",
            name="ck_inventory_items_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_inventory_items_version"),
        sa.UniqueConstraint(
            "company_id", "code", name="uq_inventory_items_company_code"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_inventory_items_company_id"),
    )
    op.create_index(
        "ix_inventory_items_catalog",
        "inventory_items",
        ["company_id", "status", "name"],
    )

    op.create_table(
        "inventory_stock_locations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("location_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("external_entity_type", sa.String(80)),
        sa.Column("external_entity_id", UUID),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        company_branch_fk("fk_inventory_locations_branch"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_inventory_locations_code",
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name="ck_inventory_locations_name"
        ),
        sa.CheckConstraint(
            "location_type IN ('warehouse','vehicle','staging','in_transit','quarantine')",
            name="ck_inventory_locations_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive','archived')",
            name="ck_inventory_locations_status",
        ),
        sa.CheckConstraint(
            "(external_entity_type IS NULL) = (external_entity_id IS NULL)",
            name="ck_inventory_locations_external_ref",
        ),
        sa.CheckConstraint("version >= 1", name="ck_inventory_locations_version"),
        sa.UniqueConstraint(
            "company_id", "code", name="uq_inventory_locations_company_code"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_inventory_locations_company_id"
        ),
        sa.UniqueConstraint(
            "company_id", "branch_id", "id", name="uq_inventory_locations_scope_id"
        ),
    )
    op.create_index(
        "ix_inventory_locations_branch",
        "inventory_stock_locations",
        ["company_id", "branch_id", "status"],
    )

    op.create_table(
        "inventory_quantities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("location_id", UUID, nullable=False),
        sa.Column("on_hand", sa.Numeric(18, 6), nullable=False),
        sa.Column("reserved", sa.Numeric(18, 6), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        company_branch_fk("fk_inventory_quantities_branch"),
        sa.ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_quantities_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_quantities_location",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("on_hand >= 0", name="ck_inventory_quantities_on_hand"),
        sa.CheckConstraint(
            "reserved >= 0 AND reserved <= on_hand",
            name="ck_inventory_quantities_reserved",
        ),
        sa.CheckConstraint("version >= 1", name="ck_inventory_quantities_version"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "item_id",
            "location_id",
            name="uq_inventory_quantities_scope",
        ),
    )
    op.create_index(
        "ix_inventory_quantities_item",
        "inventory_quantities",
        ["company_id", "item_id", "branch_id"],
    )

    op.create_table(
        "inventory_stock_movements",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("movement_type", sa.String(24), nullable=False),
        sa.Column("source_location_id", UUID),
        sa.Column("destination_location_id", UUID),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("stocking_unit", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("provenance_type", sa.String(80)),
        sa.Column("provenance_id", UUID),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("reversal_of_id", UUID),
        sa.Column("unit_cost", sa.Numeric(18, 4)),
        sa.Column("currency", sa.String(3)),
        sa.Column("valuation_method", sa.String(40)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        company_branch_fk("fk_inventory_movements_branch"),
        sa.ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_movements_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "source_location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_movements_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "destination_location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_movements_destination",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reversal_of_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_inventory_movements_reversal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "movement_type IN ('opening','increase','decrease','transfer','adjustment_in','adjustment_out')",
            name="ck_inventory_movements_type",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_movements_quantity"),
        sa.CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_movements_unit"
        ),
        sa.CheckConstraint(
            "(unit_cost IS NULL AND currency IS NULL AND valuation_method IS NULL) OR (unit_cost >= 0 AND currency ~ '^[A-Z]{3}$' AND valuation_method IS NOT NULL)",
            name="ck_inventory_movements_valuation",
        ),
        sa.CheckConstraint(
            "(provenance_type IS NULL) = (provenance_id IS NULL)",
            name="ck_inventory_movements_provenance",
        ),
        sa.CheckConstraint(
            "(movement_type = 'transfer' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type IN ('opening','increase','adjustment_in') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR (movement_type IN ('decrease','adjustment_out') AND source_location_id IS NOT NULL AND destination_location_id IS NULL)",
            name="ck_inventory_movements_locations",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_inventory_movements_company_id"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_inventory_movements_idempotency"
        ),
    )
    op.create_index(
        "ix_inventory_movements_history",
        "inventory_stock_movements",
        ["company_id", "item_id", "occurred_at", "id"],
    )

    op.create_table(
        "inventory_reservations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("location_id", UUID, nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("stocking_unit", sa.String(40), nullable=False),
        sa.Column("demand_type", sa.String(80), nullable=False),
        sa.Column("demand_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        company_branch_fk("fk_inventory_reservations_branch"),
        sa.ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_reservations_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_reservations_location",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity"),
        sa.CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_reservations_unit"
        ),
        sa.CheckConstraint(
            "length(btrim(demand_type)) > 0",
            name="ck_inventory_reservations_demand_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','released','fulfilled','expired','cancelled')",
            name="ck_inventory_reservations_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_inventory_reservations_version"),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_reservations_idempotency",
        ),
    )
    op.create_index(
        "ix_inventory_reservations_active",
        "inventory_reservations",
        ["company_id", "branch_id", "item_id", "location_id", "status"],
    )

    op.execute("""
        CREATE FUNCTION reject_inventory_movement_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'inventory movement evidence is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_inventory_movements_immutable BEFORE UPDATE OR DELETE ON inventory_stock_movements FOR EACH ROW EXECUTE FUNCTION reject_inventory_movement_mutation()"
    )
    op.execute("""
        CREATE FUNCTION protect_inventory_stocking_unit() RETURNS trigger AS $$
        BEGIN
            IF NEW.stocking_unit <> OLD.stocking_unit AND EXISTS (
                SELECT 1 FROM inventory_stock_movements
                WHERE company_id = OLD.company_id AND item_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'inventory stocking unit is immutable after movement';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_inventory_item_unit_immutable BEFORE UPDATE OF stocking_unit ON inventory_items FOR EACH ROW EXECUTE FUNCTION protect_inventory_stocking_unit()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_inventory_item_unit_immutable ON inventory_items")
    op.execute("DROP FUNCTION protect_inventory_stocking_unit()")
    op.execute(
        "DROP TRIGGER trg_inventory_movements_immutable ON inventory_stock_movements"
    )
    op.execute("DROP FUNCTION reject_inventory_movement_mutation()")
    op.drop_table("inventory_reservations")
    op.drop_table("inventory_stock_movements")
    op.drop_table("inventory_quantities")
    op.drop_table("inventory_stock_locations")
    op.drop_table("inventory_items")
