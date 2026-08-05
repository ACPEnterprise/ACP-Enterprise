from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_inventory_items_code",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="ck_inventory_items_name"),
        CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_items_unit"
        ),
        CheckConstraint(
            "status IN ('draft','active','inactive','archived')",
            name="ck_inventory_items_status",
        ),
        CheckConstraint("version >= 1", name="ck_inventory_items_version"),
        UniqueConstraint("company_id", "code", name="uq_inventory_items_company_code"),
        UniqueConstraint("company_id", "id", name="uq_inventory_items_company_id"),
        Index("ix_inventory_items_catalog", "company_id", "status", "name"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    stocking_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    allow_fractional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class StockLocation(Base):
    __tablename__ = "inventory_stock_locations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_locations_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_inventory_locations_code",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="ck_inventory_locations_name"),
        CheckConstraint(
            "location_type IN ('warehouse','vehicle','staging','in_transit','quarantine')",
            name="ck_inventory_locations_type",
        ),
        CheckConstraint(
            "status IN ('active','inactive','archived')",
            name="ck_inventory_locations_status",
        ),
        CheckConstraint(
            "(external_entity_type IS NULL) = (external_entity_id IS NULL)",
            name="ck_inventory_locations_external_ref",
        ),
        CheckConstraint("version >= 1", name="ck_inventory_locations_version"),
        UniqueConstraint(
            "company_id", "code", name="uq_inventory_locations_company_code"
        ),
        UniqueConstraint("company_id", "id", name="uq_inventory_locations_company_id"),
        UniqueConstraint(
            "company_id", "branch_id", "id", name="uq_inventory_locations_scope_id"
        ),
        Index("ix_inventory_locations_branch", "company_id", "branch_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    location_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    external_entity_type: Mapped[str | None] = mapped_column(String(80))
    external_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class InventoryQuantity(Base):
    __tablename__ = "inventory_quantities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_quantities_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_quantities_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_quantities_location",
            ondelete="RESTRICT",
        ),
        CheckConstraint("on_hand >= 0", name="ck_inventory_quantities_on_hand"),
        CheckConstraint(
            "reserved >= 0 AND reserved <= on_hand",
            name="ck_inventory_quantities_reserved",
        ),
        CheckConstraint("version >= 1", name="ck_inventory_quantities_version"),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "item_id",
            "location_id",
            name="uq_inventory_quantities_scope",
        ),
        Index("ix_inventory_quantities_item", "company_id", "item_id", "branch_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(0)
    )
    reserved: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(0)
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class StockMovement(Base):
    __tablename__ = "inventory_stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_movements_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_movements_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "source_location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_movements_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "destination_location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_movements_destination",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reversal_of_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_inventory_movements_reversal",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "movement_type IN ('opening','increase','decrease','transfer','adjustment_in','adjustment_out')",
            name="ck_inventory_movements_type",
        ),
        CheckConstraint("quantity > 0", name="ck_inventory_movements_quantity"),
        CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_movements_unit"
        ),
        CheckConstraint(
            "(unit_cost IS NULL AND currency IS NULL AND valuation_method IS NULL) OR (unit_cost >= 0 AND currency ~ '^[A-Z]{3}$' AND valuation_method IS NOT NULL)",
            name="ck_inventory_movements_valuation",
        ),
        CheckConstraint(
            "(provenance_type IS NULL) = (provenance_id IS NULL)",
            name="ck_inventory_movements_provenance",
        ),
        CheckConstraint(
            "(movement_type = 'transfer' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type IN ('opening','increase','adjustment_in') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR (movement_type IN ('decrease','adjustment_out') AND source_location_id IS NOT NULL AND destination_location_id IS NULL)",
            name="ck_inventory_movements_locations",
        ),
        UniqueConstraint("company_id", "id", name="uq_inventory_movements_company_id"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_inventory_movements_idempotency"
        ),
        Index(
            "ix_inventory_movements_history",
            "company_id",
            "item_id",
            "occurred_at",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    destination_location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stocking_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provenance_type: Mapped[str | None] = mapped_column(String(80))
    provenance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    reversal_of_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str | None] = mapped_column(String(3))
    valuation_method: Mapped[str | None] = mapped_column(String(40))


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_reservations_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_reservations_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_reservations_location",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity"),
        CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_reservations_unit"
        ),
        CheckConstraint(
            "length(btrim(demand_type)) > 0",
            name="ck_inventory_reservations_demand_type",
        ),
        CheckConstraint(
            "status IN ('active','released','fulfilled','expired','cancelled')",
            name="ck_inventory_reservations_status",
        ),
        CheckConstraint("version >= 1", name="ck_inventory_reservations_version"),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_reservations_idempotency",
        ),
        Index(
            "ix_inventory_reservations_active",
            "company_id",
            "branch_id",
            "item_id",
            "location_id",
            "status",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stocking_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    demand_type: Mapped[str] = mapped_column(String(80), nullable=False)
    demand_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
