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


class InventoryOverview(InventorySchema):
    items: tuple[ItemResponse, ...]
    locations: tuple[LocationResponse, ...]
    quantities: tuple[QuantityResponse, ...]
    reservations: tuple[ReservationResponse, ...]
