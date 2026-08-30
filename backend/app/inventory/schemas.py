from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class InventorySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class LocationCreate(InventorySchema):
    branch_id: UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    location_type: str
    external_entity_type: str | None = None
    external_entity_id: UUID | None = None


class TransferCreate(InventorySchema):
    branch_id: UUID
    item_id: UUID
    source_location_id: UUID
    destination_location_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    occurred_at: AwareDatetime
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReservationCreate(InventorySchema):
    branch_id: UUID
    item_id: UUID
    location_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    demand_type: str = Field(min_length=1, max_length=80)
    demand_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    expires_at: AwareDatetime | None = None


class ReservationAllocate(InventorySchema):
    quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    allow_partial: bool = False
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReservationRelease(InventorySchema):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class AdjustmentCreate(InventorySchema):
    branch_id: UUID
    item_id: UUID
    location_id: UUID
    reason: str = Field(pattern=r"^(gain|loss|damaged|expired|found)$")
    quantity_delta: Decimal = Field(max_digits=18, decimal_places=6)
    note: str = Field(min_length=1, max_length=1000)
    occurred_at: AwareDatetime
    idempotency_key: str = Field(min_length=1, max_length=128)


class CycleCountStart(InventorySchema):
    branch_id: UUID
    location_id: UUID
    name: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=128)


class CycleCountRecord(InventorySchema):
    item_id: UUID
    counted_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    counted_at: AwareDatetime
    idempotency_key: str = Field(min_length=1, max_length=128)


class CycleCountComplete(InventorySchema):
    expected_version: int = Field(ge=1)


class ItemResponse(InventorySchema):
    id: UUID
    company_id: UUID
    code: str
    name: str
    stocking_unit: str
    allow_fractional: bool
    status: str
    version: int


class LocationResponse(InventorySchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    code: str
    name: str
    location_type: str
    status: str
    external_entity_type: str | None
    external_entity_id: UUID | None
    version: int


class QuantityResponse(InventorySchema):
    item_id: UUID
    location_id: UUID
    company_id: UUID
    branch_id: UUID
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    version: int
    updated_at: datetime


class ReservationResponse(InventorySchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    item_id: UUID
    location_id: UUID
    quantity: Decimal
    allocated_quantity: Decimal
    issued_quantity: Decimal
    stocking_unit: str
    demand_type: str
    demand_id: UUID
    status: str
    expires_at: datetime | None
    idempotency_key: str
    version: int
    created_at: datetime
    updated_at: datetime


class MovementResponse(InventorySchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    item_id: UUID
    movement_type: str
    source_location_id: UUID | None
    destination_location_id: UUID | None
    quantity: Decimal
    stocking_unit: str
    occurred_at: datetime
    posted_at: datetime
    idempotency_key: str


class AllocationResponse(InventorySchema):
    id: UUID
    reservation_id: UUID
    item_id: UUID
    location_id: UUID
    quantity: Decimal
    requested_quantity: Decimal
    partial_allowed: bool
    reservation_version: int
    allocated_at: datetime


class AdjustmentResponse(InventorySchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    item_id: UUID
    location_id: UUID
    reason: str
    quantity_delta: Decimal
    stocking_unit: str
    note: str
    occurred_at: datetime
    posted_at: datetime
    actor_user_id: UUID
    idempotency_key: str
    movement_id: UUID
    cycle_count_entry_id: UUID | None


class CycleCountEntryResponse(InventorySchema):
    id: UUID
    company_id: UUID
    session_id: UUID
    item_id: UUID
    expected_quantity: Decimal
    counted_quantity: Decimal
    variance: Decimal
    stocking_unit: str
    counted_at: datetime
    counted_by_user_id: UUID
    idempotency_key: str


class CycleCountSessionResponse(InventorySchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    location_id: UUID
    name: str
    status: str
    idempotency_key: str
    version: int
    started_by_user_id: UUID
    completed_by_user_id: UUID | None
    started_at: datetime
    completed_at: datetime | None
    entries: tuple[CycleCountEntryResponse, ...] = ()


class InventoryOverview(InventorySchema):
    items: tuple[ItemResponse, ...]
    locations: tuple[LocationResponse, ...]
    quantities: tuple[QuantityResponse, ...]
    reservations: tuple[ReservationResponse, ...]
