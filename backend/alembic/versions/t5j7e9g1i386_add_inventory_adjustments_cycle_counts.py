"""add inventory adjustments and cycle counts

Revision ID: t5j7e9g1i386
Revises: s4i6d8f0h275
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "t5j7e9g1i386"
down_revision: str | None = "s4i6d8f0h275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "inventory_cycle_count_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("location_id", UUID, nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_by_user_id", UUID, nullable=False),
        sa.Column("completed_by_user_id", UUID),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_cycle_sessions_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_cycle_sessions_location",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('open','completed')", name="ck_inventory_cycle_sessions_status"
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name="ck_inventory_cycle_sessions_name"
        ),
        sa.CheckConstraint("version >= 1", name="ck_inventory_cycle_sessions_version"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_inventory_cycle_sessions_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_cycle_sessions_idempotency",
        ),
    )
    op.create_index(
        "ix_inventory_cycle_sessions_scope",
        "inventory_cycle_count_sessions",
        ["company_id", "branch_id", "location_id", "status"],
    )

    op.create_table(
        "inventory_cycle_count_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("expected_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("stocking_unit", sa.String(40), nullable=False),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("counted_by_user_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "session_id"],
            [
                "inventory_cycle_count_sessions.company_id",
                "inventory_cycle_count_sessions.id",
            ],
            name="fk_inventory_cycle_entries_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_cycle_entries_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["counted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "expected_quantity >= 0", name="ck_inventory_cycle_entries_expected"
        ),
        sa.CheckConstraint(
            "counted_quantity >= 0", name="ck_inventory_cycle_entries_counted"
        ),
        sa.CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_cycle_entries_unit"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_inventory_cycle_entries_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "session_id",
            "item_id",
            name="uq_inventory_cycle_entries_item",
        ),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_cycle_entries_idempotency",
        ),
    )
    op.create_index(
        "ix_inventory_cycle_entries_session",
        "inventory_cycle_count_entries",
        ["company_id", "session_id", "id"],
    )

    op.create_table(
        "inventory_adjustments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("location_id", UUID, nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(18, 6), nullable=False),
        sa.Column("stocking_unit", sa.String(40), nullable=False),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("movement_id", UUID, nullable=False),
        sa.Column("cycle_count_entry_id", UUID),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_adjustments_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_adjustments_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_adjustments_location",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "movement_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_inventory_adjustments_movement",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "cycle_count_entry_id"],
            [
                "inventory_cycle_count_entries.company_id",
                "inventory_cycle_count_entries.id",
            ],
            name="fk_inventory_adjustments_cycle_entry",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "reason IN ('gain','loss','damaged','expired','found')",
            name="ck_inventory_adjustments_reason",
        ),
        sa.CheckConstraint(
            "quantity_delta <> 0", name="ck_inventory_adjustments_delta"
        ),
        sa.CheckConstraint(
            "(reason IN ('gain','found') AND quantity_delta > 0) OR (reason IN ('loss','damaged','expired') AND quantity_delta < 0)",
            name="ck_inventory_adjustments_direction",
        ),
        sa.CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_adjustments_unit"
        ),
        sa.CheckConstraint(
            "length(btrim(note)) > 0", name="ck_inventory_adjustments_note"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_inventory_adjustments_company_id"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_inventory_adjustments_idempotency"
        ),
        sa.UniqueConstraint(
            "company_id", "movement_id", name="uq_inventory_adjustments_movement"
        ),
    )
    op.create_index(
        "ix_inventory_adjustments_history",
        "inventory_adjustments",
        ["company_id", "branch_id", "item_id", "location_id", "occurred_at"],
    )

    op.execute("""
        CREATE FUNCTION reject_inventory_adjustment_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'inventory adjustment evidence is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_inventory_adjustments_immutable BEFORE UPDATE OR DELETE ON inventory_adjustments FOR EACH ROW EXECUTE FUNCTION reject_inventory_adjustment_mutation()"
    )
    op.execute("""
        CREATE FUNCTION reject_cycle_count_entry_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'cycle count entry evidence is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_inventory_cycle_entries_immutable BEFORE UPDATE OR DELETE ON inventory_cycle_count_entries FOR EACH ROW EXECUTE FUNCTION reject_cycle_count_entry_mutation()"
    )
    op.execute("""
        CREATE FUNCTION protect_cycle_count_session() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'cycle count session history is immutable';
            END IF;
            IF OLD.status = 'completed'
                OR NEW.company_id <> OLD.company_id
                OR NEW.branch_id <> OLD.branch_id
                OR NEW.location_id <> OLD.location_id
                OR NEW.name <> OLD.name
                OR NEW.idempotency_key <> OLD.idempotency_key
                OR NEW.started_by_user_id <> OLD.started_by_user_id
                OR NEW.started_at <> OLD.started_at
                OR NEW.status <> 'completed'
                OR NEW.completed_by_user_id IS NULL
                OR NEW.completed_at IS NULL
                OR NEW.version <> OLD.version + 1
            THEN
                RAISE EXCEPTION 'cycle count session transition is invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_inventory_cycle_sessions_controlled BEFORE UPDATE OR DELETE ON inventory_cycle_count_sessions FOR EACH ROW EXECUTE FUNCTION protect_cycle_count_session()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_inventory_cycle_sessions_controlled ON inventory_cycle_count_sessions"
    )
    op.execute("DROP FUNCTION protect_cycle_count_session()")
    op.execute(
        "DROP TRIGGER trg_inventory_cycle_entries_immutable ON inventory_cycle_count_entries"
    )
    op.execute("DROP FUNCTION reject_cycle_count_entry_mutation()")
    op.execute(
        "DROP TRIGGER trg_inventory_adjustments_immutable ON inventory_adjustments"
    )
    op.execute("DROP FUNCTION reject_inventory_adjustment_mutation()")
    op.drop_table("inventory_adjustments")
    op.drop_table("inventory_cycle_count_entries")
    op.drop_table("inventory_cycle_count_sessions")
