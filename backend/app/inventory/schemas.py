from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class InventorySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ItemCreate(InventorySchema):
    name: str = Field(min_length=1, max_length=240)
    stocking_unit: str = Field(min_length=1, max_length=40)
    allow_fractional: bool = True


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


class MaterialIssueCreate(InventorySchema):
    branch_id: UUID
    allocation_id: UUID
    item_id: UUID
    location_id: UUID
    expected_reservation_version: int = Field(ge=1)
    occurred_at: AwareDatetime
    idempotency_key: str = Field(min_length=1, max_length=128)


class MaterialIssueReverse(InventorySchema):
    branch_id: UUID
    expected_reservation_version: int = Field(ge=1)
    occurred_at: AwareDatetime
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


class JobMaterialRequirementResponse(InventorySchema):
    component_code: str | None
    label: str
    requirement_type: str
    expected_quantity: Decimal
    inventory_item_id: UUID | None
    stocking_unit: str | None
    on_hand_quantity: Decimal | None
    reserved_quantity: Decimal | None
    available_quantity: Decimal | None
    consumed_quantity: Decimal | None
    readiness_state: str
    blockers: tuple[str, ...]
    source_snapshot_ids: tuple[UUID, ...]
    source_snapshot_digests: tuple[str, ...]


class JobMaterialsResponse(InventorySchema):
    job_id: UUID
    branch_id: UUID
    requirements: tuple[JobMaterialRequirementResponse, ...]
    readiness_state: str
    blockers: tuple[str, ...]


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


class MaterialIssueResponse(InventorySchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    reservation_id: UUID
    allocation_id: UUID
    issue_type: str
    item_id: UUID
    location_id: UUID
    quantity: Decimal
    stocking_unit: str
    occurred_at: datetime
    posted_at: datetime
    actor_user_id: UUID
    idempotency_key: str
    movement_id: UUID
    reversal_of_issue_id: UUID | None
    external_reference_type: str | None
    external_reference_id: UUID | None


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
    allocations: tuple[AllocationResponse, ...] = ()
    material_issues: tuple[MaterialIssueResponse, ...] = ()


class MaterialCostEvidenceResponse(InventorySchema):
    inventory_item_id: UUID
    vendor_id: UUID
    vendor_name: str
    purchase_order_id: UUID
    purchase_order_line_id: UUID
    receipt_id: UUID
    receipt_line_id: UUID
    received_at: datetime
    effective_date: date
    accepted_quantity: Decimal
    unit: str
    unit_cost: Decimal
    currency: str
    source_reference: str | None
    authority_state: str = "ACTUAL_RECEIPT"


class MaterialValuationReadinessResponse(InventorySchema):
    inventory_item_id: UUID
    on_hand_quantity: Decimal
    actual_receipt_cost_available: bool
    currencies: tuple[str, ...]
    readiness_state: str
    blockers: tuple[str, ...]


class MaterialCostReadinessResponse(InventorySchema):
    evidence: tuple[MaterialCostEvidenceResponse, ...]
    readiness: tuple[MaterialValuationReadinessResponse, ...]
