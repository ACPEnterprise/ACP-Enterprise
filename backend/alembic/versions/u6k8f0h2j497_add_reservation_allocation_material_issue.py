"""add reservation allocation and material issue foundation

Revision ID: u6k8f0h2j497
Revises: v7l9h1d3e508
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "u6k8f0h2j497"
down_revision: str | None = "v7l9h1d3e508"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


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
        "movement_type IN ('opening','increase','decrease','transfer','adjustment_in','adjustment_out','material_issue','material_issue_reversal')",
    )
    op.create_check_constraint(
        "ck_inventory_movements_locations",
        "inventory_stock_movements",
        "(movement_type = 'transfer' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type IN ('opening','increase','adjustment_in','material_issue_reversal') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR (movement_type IN ('decrease','adjustment_out','material_issue') AND source_location_id IS NOT NULL AND destination_location_id IS NULL)",
    )

    op.drop_constraint(
        "ck_inventory_reservations_status", "inventory_reservations", type_="check"
    )
    op.add_column(
        "inventory_reservations",
        sa.Column(
            "allocated_quantity",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "inventory_reservations",
        sa.Column(
            "issued_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"
        ),
    )
    op.execute(
        "UPDATE inventory_reservations SET status = 'allocated', allocated_quantity = quantity WHERE status = 'active'"
    )
    op.execute(
        "UPDATE inventory_reservations SET status = 'cancelled', allocated_quantity = quantity WHERE status = 'expired'"
    )
    op.alter_column("inventory_reservations", "allocated_quantity", server_default=None)
    op.alter_column("inventory_reservations", "issued_quantity", server_default=None)
    op.create_check_constraint(
        "ck_inventory_reservations_status",
        "inventory_reservations",
        "status IN ('requested','allocated','partially_allocated','released','fulfilled','cancelled')",
    )
    op.create_check_constraint(
        "ck_inventory_reservations_allocated",
        "inventory_reservations",
        "allocated_quantity >= 0 AND allocated_quantity <= quantity",
    )
    op.create_check_constraint(
        "ck_inventory_reservations_issued",
        "inventory_reservations",
        "issued_quantity >= 0 AND issued_quantity <= allocated_quantity",
    )
    op.create_unique_constraint(
        "uq_inventory_reservations_company_id",
        "inventory_reservations",
        ["company_id", "id"],
    )
    op.create_unique_constraint(
        "uq_inventory_reservations_scope_id",
        "inventory_reservations",
        ["company_id", "branch_id", "item_id", "location_id", "id"],
    )

    op.create_table(
        "inventory_reservation_allocations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("reservation_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("location_id", UUID, nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("partial_allowed", sa.Boolean(), nullable=False),
        sa.Column("stocking_unit", sa.String(40), nullable=False),
        sa.Column("reservation_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("allocated_by_user_id", UUID, nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_allocations_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_allocations_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_allocations_location",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "item_id", "location_id", "reservation_id"],
            [
                "inventory_reservations.company_id",
                "inventory_reservations.branch_id",
                "inventory_reservations.item_id",
                "inventory_reservations.location_id",
                "inventory_reservations.id",
            ],
            name="fk_inventory_allocations_reservation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["allocated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_allocations_quantity"),
        sa.CheckConstraint(
            "requested_quantity > 0 AND quantity <= requested_quantity",
            name="ck_inventory_allocations_requested",
        ),
        sa.CheckConstraint(
            "length(btrim(stocking_unit)) > 0",
            name="ck_inventory_allocations_unit",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_inventory_allocations_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "reservation_id",
            "item_id",
            "location_id",
            "id",
            name="uq_inventory_allocations_scope_id",
        ),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_allocations_idempotency",
        ),
    )
    op.create_index(
        "ix_inventory_allocations_reservation",
        "inventory_reservation_allocations",
        ["company_id", "reservation_id", "allocated_at", "id"],
    )

    op.create_table(
        "inventory_reservation_lifecycle_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("reservation_id", UUID, nullable=False),
        sa.Column("from_status", sa.String(24), nullable=False),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "reservation_id"],
            ["inventory_reservations.company_id", "inventory_reservations.id"],
            name="fk_inventory_reservation_events_reservation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "from_status IN ('requested','allocated','partially_allocated','released','fulfilled','cancelled')",
            name="ck_inventory_reservation_events_from",
        ),
        sa.CheckConstraint(
            "to_status IN ('requested','allocated','partially_allocated','released','fulfilled','cancelled')",
            name="ck_inventory_reservation_events_to",
        ),
        sa.CheckConstraint(
            "from_status <> to_status", name="ck_inventory_reservation_events_change"
        ),
        sa.CheckConstraint(
            "from_version >= 1", name="ck_inventory_reservation_events_version"
        ),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_reservation_events_idempotency",
        ),
    )
    op.create_index(
        "ix_inventory_reservation_events_history",
        "inventory_reservation_lifecycle_events",
        ["company_id", "reservation_id", "occurred_at", "id"],
    )

    op.create_table(
        "inventory_material_issues",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("reservation_id", UUID, nullable=False),
        sa.Column("allocation_id", UUID, nullable=False),
        sa.Column("issue_type", sa.String(20), nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("location_id", UUID, nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("stocking_unit", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("movement_id", UUID, nullable=False),
        sa.Column("reversal_of_issue_id", UUID),
        sa.Column("external_reference_type", sa.String(80)),
        sa.Column("external_reference_id", UUID),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_issues_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "item_id", "location_id", "reservation_id"],
            [
                "inventory_reservations.company_id",
                "inventory_reservations.branch_id",
                "inventory_reservations.item_id",
                "inventory_reservations.location_id",
                "inventory_reservations.id",
            ],
            name="fk_inventory_issues_reservation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reservation_id", "item_id", "location_id", "allocation_id"],
            [
                "inventory_reservation_allocations.company_id",
                "inventory_reservation_allocations.reservation_id",
                "inventory_reservation_allocations.item_id",
                "inventory_reservation_allocations.location_id",
                "inventory_reservation_allocations.id",
            ],
            name="fk_inventory_issues_allocation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "movement_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_inventory_issues_movement",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reversal_of_issue_id"],
            ["inventory_material_issues.company_id", "inventory_material_issues.id"],
            name="fk_inventory_issues_reversal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "issue_type IN ('issue','reversal')", name="ck_inventory_issues_type"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_issues_quantity"),
        sa.CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_issues_unit"
        ),
        sa.CheckConstraint(
            "(issue_type = 'issue' AND reversal_of_issue_id IS NULL) OR (issue_type = 'reversal' AND reversal_of_issue_id IS NOT NULL)",
            name="ck_inventory_issues_reversal_shape",
        ),
        sa.CheckConstraint(
            "(external_reference_type IS NULL) = (external_reference_id IS NULL)",
            name="ck_inventory_issues_external_reference",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_inventory_issues_company_id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_inventory_issues_idempotency"
        ),
        sa.UniqueConstraint(
            "company_id", "movement_id", name="uq_inventory_issues_movement"
        ),
        sa.UniqueConstraint(
            "company_id",
            "allocation_id",
            "issue_type",
            name="uq_inventory_issues_allocation_type",
        ),
        sa.UniqueConstraint(
            "company_id", "reversal_of_issue_id", name="uq_inventory_issues_reversal"
        ),
    )
    op.create_index(
        "ix_inventory_issues_history",
        "inventory_material_issues",
        ["company_id", "reservation_id", "occurred_at", "id"],
    )

    op.execute("""
        CREATE FUNCTION reject_inv3_evidence_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'inventory allocation and issue evidence is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    for table, trigger in (
        ("inventory_reservation_allocations", "trg_inventory_allocations_immutable"),
        (
            "inventory_reservation_lifecycle_events",
            "trg_inventory_reservation_events_immutable",
        ),
        ("inventory_material_issues", "trg_inventory_material_issues_immutable"),
    ):
        op.execute(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_inv3_evidence_mutation()"
        )
    op.execute("""
        CREATE FUNCTION protect_inventory_reservation_lifecycle() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'inventory reservation history cannot be deleted';
            END IF;
            IF NEW.company_id <> OLD.company_id
                OR NEW.branch_id <> OLD.branch_id
                OR NEW.item_id <> OLD.item_id
                OR NEW.location_id <> OLD.location_id
                OR NEW.quantity <> OLD.quantity
                OR NEW.stocking_unit <> OLD.stocking_unit
                OR NEW.demand_type <> OLD.demand_type
                OR NEW.demand_id <> OLD.demand_id
                OR NEW.idempotency_key <> OLD.idempotency_key
                OR NEW.created_by_user_id <> OLD.created_by_user_id
                OR NEW.created_at <> OLD.created_at
                OR NEW.version <> OLD.version + 1
                OR NOT (
                    (OLD.status = 'requested' AND NEW.status IN ('partially_allocated','allocated','released','cancelled'))
                    OR (OLD.status = 'partially_allocated' AND NEW.status IN ('partially_allocated','allocated','released','cancelled'))
                    OR (OLD.status = 'allocated' AND NEW.status IN ('allocated','fulfilled','released','cancelled'))
                    OR (OLD.status = 'fulfilled' AND NEW.status = 'allocated')
                )
            THEN
                RAISE EXCEPTION 'inventory reservation lifecycle transition is invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_inventory_reservations_lifecycle BEFORE UPDATE OR DELETE "
        "ON inventory_reservations FOR EACH ROW EXECUTE FUNCTION "
        "protect_inventory_reservation_lifecycle()"
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM inventory_stock_movements
                WHERE movement_type IN ('material_issue','material_issue_reversal')
            ) THEN
                RAISE EXCEPTION 'cannot downgrade INV.3 while material issue movement evidence exists';
            END IF;
        END $$
    """)
    op.execute(
        "DROP TRIGGER trg_inventory_reservations_lifecycle ON inventory_reservations"
    )
    op.execute("DROP FUNCTION protect_inventory_reservation_lifecycle()")
    for table, trigger in (
        ("inventory_material_issues", "trg_inventory_material_issues_immutable"),
        (
            "inventory_reservation_lifecycle_events",
            "trg_inventory_reservation_events_immutable",
        ),
        ("inventory_reservation_allocations", "trg_inventory_allocations_immutable"),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
    op.execute("DROP FUNCTION reject_inv3_evidence_mutation()")
    op.drop_table("inventory_material_issues")
    op.drop_table("inventory_reservation_lifecycle_events")
    op.drop_table("inventory_reservation_allocations")

    op.execute(
        "UPDATE inventory_reservations SET status = 'active' WHERE status IN ('requested','allocated','partially_allocated')"
    )
    op.drop_constraint(
        "uq_inventory_reservations_scope_id", "inventory_reservations", type_="unique"
    )
    op.drop_constraint(
        "uq_inventory_reservations_company_id", "inventory_reservations", type_="unique"
    )
    op.drop_constraint(
        "ck_inventory_reservations_issued", "inventory_reservations", type_="check"
    )
    op.drop_constraint(
        "ck_inventory_reservations_allocated", "inventory_reservations", type_="check"
    )
    op.drop_constraint(
        "ck_inventory_reservations_status", "inventory_reservations", type_="check"
    )
    op.create_check_constraint(
        "ck_inventory_reservations_status",
        "inventory_reservations",
        "status IN ('active','released','fulfilled','expired','cancelled')",
    )
    op.drop_column("inventory_reservations", "issued_quantity")
    op.drop_column("inventory_reservations", "allocated_quantity")

    op.drop_constraint(
        "ck_inventory_movements_locations", "inventory_stock_movements", type_="check"
    )
    op.drop_constraint(
        "ck_inventory_movements_type", "inventory_stock_movements", type_="check"
    )
    op.create_check_constraint(
        "ck_inventory_movements_type",
        "inventory_stock_movements",
        "movement_type IN ('opening','increase','decrease','transfer','adjustment_in','adjustment_out')",
    )
    op.create_check_constraint(
        "ck_inventory_movements_locations",
        "inventory_stock_movements",
        "(movement_type = 'transfer' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type IN ('opening','increase','adjustment_in') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR (movement_type IN ('decrease','adjustment_out') AND source_location_id IS NOT NULL AND destination_location_id IS NULL)",
    )
