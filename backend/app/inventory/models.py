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
            "movement_type IN ('opening','increase','decrease','transfer','adjustment_in','adjustment_out','material_issue','material_issue_reversal')",
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
            "(movement_type = 'transfer' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type IN ('opening','increase','adjustment_in','material_issue_reversal') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR (movement_type IN ('decrease','adjustment_out','material_issue') AND source_location_id IS NOT NULL AND destination_location_id IS NULL)",
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
            "status IN ('requested','allocated','partially_allocated','released','fulfilled','cancelled')",
            name="ck_inventory_reservations_status",
        ),
        CheckConstraint(
            "allocated_quantity >= 0 AND allocated_quantity <= quantity",
            name="ck_inventory_reservations_allocated",
        ),
        CheckConstraint(
            "issued_quantity >= 0 AND issued_quantity <= allocated_quantity",
            name="ck_inventory_reservations_issued",
        ),
        CheckConstraint("version >= 1", name="ck_inventory_reservations_version"),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_reservations_idempotency",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_inventory_reservations_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "item_id",
            "location_id",
            "id",
            name="uq_inventory_reservations_scope_id",
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
    allocated_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(0)
    )
    issued_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(0)
    )
    stocking_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    demand_type: Mapped[str] = mapped_column(String(80), nullable=False)
    demand_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
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


class ReservationAllocation(Base):
    __tablename__ = "inventory_reservation_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_allocations_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_allocations_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_allocations_location",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "company_id",
                "branch_id",
                "item_id",
                "location_id",
                "reservation_id",
            ],
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
        CheckConstraint("quantity > 0", name="ck_inventory_allocations_quantity"),
        CheckConstraint(
            "requested_quantity > 0 AND quantity <= requested_quantity",
            name="ck_inventory_allocations_requested",
        ),
        CheckConstraint(
            "length(btrim(stocking_unit)) > 0",
            name="ck_inventory_allocations_unit",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_inventory_allocations_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "reservation_id",
            "item_id",
            "location_id",
            "id",
            name="uq_inventory_allocations_scope_id",
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_allocations_idempotency",
        ),
        Index(
            "ix_inventory_allocations_reservation",
            "company_id",
            "reservation_id",
            "allocated_at",
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
    reservation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    partial_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stocking_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    reservation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    allocated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ReservationLifecycleEvent(Base):
    __tablename__ = "inventory_reservation_lifecycle_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "reservation_id"],
            ["inventory_reservations.company_id", "inventory_reservations.id"],
            name="fk_inventory_reservation_events_reservation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "from_status IN ('requested','allocated','partially_allocated','released','fulfilled','cancelled')",
            name="ck_inventory_reservation_events_from",
        ),
        CheckConstraint(
            "to_status IN ('requested','allocated','partially_allocated','released','fulfilled','cancelled')",
            name="ck_inventory_reservation_events_to",
        ),
        CheckConstraint(
            "from_status <> to_status", name="ck_inventory_reservation_events_change"
        ),
        CheckConstraint(
            "from_version >= 1", name="ck_inventory_reservation_events_version"
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_reservation_events_idempotency",
        ),
        Index(
            "ix_inventory_reservation_events_history",
            "company_id",
            "reservation_id",
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
    reservation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    from_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MaterialIssue(Base):
    __tablename__ = "inventory_material_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_issues_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
            ["company_id", "movement_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_inventory_issues_movement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reversal_of_issue_id"],
            ["inventory_material_issues.company_id", "inventory_material_issues.id"],
            name="fk_inventory_issues_reversal",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "issue_type IN ('issue','reversal')", name="ck_inventory_issues_type"
        ),
        CheckConstraint("quantity > 0", name="ck_inventory_issues_quantity"),
        CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_issues_unit"
        ),
        CheckConstraint(
            "(issue_type = 'issue' AND reversal_of_issue_id IS NULL) OR "
            "(issue_type = 'reversal' AND reversal_of_issue_id IS NOT NULL)",
            name="ck_inventory_issues_reversal_shape",
        ),
        CheckConstraint(
            "(external_reference_type IS NULL) = (external_reference_id IS NULL)",
            name="ck_inventory_issues_external_reference",
        ),
        UniqueConstraint("company_id", "id", name="uq_inventory_issues_company_id"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_inventory_issues_idempotency"
        ),
        UniqueConstraint(
            "company_id", "movement_id", name="uq_inventory_issues_movement"
        ),
        UniqueConstraint(
            "company_id",
            "allocation_id",
            "issue_type",
            name="uq_inventory_issues_allocation_type",
        ),
        UniqueConstraint(
            "company_id", "reversal_of_issue_id", name="uq_inventory_issues_reversal"
        ),
        Index(
            "ix_inventory_issues_history",
            "company_id",
            "reservation_id",
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
    reservation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    allocation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    movement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reversal_of_issue_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    external_reference_type: Mapped[str | None] = mapped_column(String(80))
    external_reference_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class InventoryAdjustment(Base):
    __tablename__ = "inventory_adjustments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_adjustments_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_adjustments_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_adjustments_location",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "movement_id"],
            ["inventory_stock_movements.company_id", "inventory_stock_movements.id"],
            name="fk_inventory_adjustments_movement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "cycle_count_entry_id"],
            [
                "inventory_cycle_count_entries.company_id",
                "inventory_cycle_count_entries.id",
            ],
            name="fk_inventory_adjustments_cycle_entry",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "reason IN ('gain','loss','damaged','expired','found')",
            name="ck_inventory_adjustments_reason",
        ),
        CheckConstraint("quantity_delta <> 0", name="ck_inventory_adjustments_delta"),
        CheckConstraint(
            "(reason IN ('gain','found') AND quantity_delta > 0) OR "
            "(reason IN ('loss','damaged','expired') AND quantity_delta < 0)",
            name="ck_inventory_adjustments_direction",
        ),
        CheckConstraint(
            "length(btrim(stocking_unit)) > 0",
            name="ck_inventory_adjustments_unit",
        ),
        CheckConstraint(
            "length(btrim(note)) > 0", name="ck_inventory_adjustments_note"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_inventory_adjustments_company_id"
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_inventory_adjustments_idempotency"
        ),
        UniqueConstraint(
            "company_id", "movement_id", name="uq_inventory_adjustments_movement"
        ),
        Index(
            "ix_inventory_adjustments_history",
            "company_id",
            "branch_id",
            "item_id",
            "location_id",
            "occurred_at",
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
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stocking_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=False)
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
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    movement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    cycle_count_entry_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class CycleCountSession(Base):
    __tablename__ = "inventory_cycle_count_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_inventory_cycle_sessions_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "location_id"],
            [
                "inventory_stock_locations.company_id",
                "inventory_stock_locations.branch_id",
                "inventory_stock_locations.id",
            ],
            name="fk_inventory_cycle_sessions_location",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('open','completed')", name="ck_inventory_cycle_sessions_status"
        ),
        CheckConstraint(
            "length(btrim(name)) > 0", name="ck_inventory_cycle_sessions_name"
        ),
        CheckConstraint("version >= 1", name="ck_inventory_cycle_sessions_version"),
        UniqueConstraint(
            "company_id", "id", name="uq_inventory_cycle_sessions_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_cycle_sessions_idempotency",
        ),
        Index(
            "ix_inventory_cycle_sessions_scope",
            "company_id",
            "branch_id",
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
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CycleCountEntry(Base):
    __tablename__ = "inventory_cycle_count_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "session_id"],
            [
                "inventory_cycle_count_sessions.company_id",
                "inventory_cycle_count_sessions.id",
            ],
            name="fk_inventory_cycle_entries_session",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "item_id"],
            ["inventory_items.company_id", "inventory_items.id"],
            name="fk_inventory_cycle_entries_item",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "expected_quantity >= 0", name="ck_inventory_cycle_entries_expected"
        ),
        CheckConstraint(
            "counted_quantity >= 0", name="ck_inventory_cycle_entries_counted"
        ),
        CheckConstraint(
            "length(btrim(stocking_unit)) > 0", name="ck_inventory_cycle_entries_unit"
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_inventory_cycle_entries_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "session_id",
            "item_id",
            name="uq_inventory_cycle_entries_item",
        ),
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_inventory_cycle_entries_idempotency",
        ),
        Index("ix_inventory_cycle_entries_session", "company_id", "session_id", "id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stocking_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    counted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    counted_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
