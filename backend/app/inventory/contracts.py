from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class CreateInventoryItem:
    company_id: UUID
    code: str
    name: str
    stocking_unit: str
    actor_user_id: UUID
    allow_fractional: bool = True


@dataclass(frozen=True, slots=True)
class CreateStockLocation:
    company_id: UUID
    branch_id: UUID
    code: str
    name: str
    location_type: str
    actor_user_id: UUID
    external_entity_type: str | None = None
    external_entity_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PostStockMovement:
    company_id: UUID
    branch_id: UUID
    item_id: UUID
    movement_type: str
    quantity: Decimal
    occurred_at: datetime
    actor_user_id: UUID
    idempotency_key: str
    source_location_id: UUID | None = None
    destination_location_id: UUID | None = None
    provenance_type: str | None = None
    provenance_id: UUID | None = None
    reversal_of_id: UUID | None = None
    unit_cost: Decimal | None = None
    currency: str | None = None
    valuation_method: str | None = None


@dataclass(frozen=True, slots=True)
class CreateReservation:
    company_id: UUID
    branch_id: UUID
    item_id: UUID
    location_id: UUID
    quantity: Decimal
    demand_type: str
    demand_id: UUID
    actor_user_id: UUID
    idempotency_key: str
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PostInventoryAdjustment:
    company_id: UUID
    branch_id: UUID
    item_id: UUID
    location_id: UUID
    reason: str
    quantity_delta: Decimal
    note: str
    occurred_at: datetime
    actor_user_id: UUID
    idempotency_key: str
    cycle_count_entry_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class StartCycleCount:
    company_id: UUID
    branch_id: UUID
    location_id: UUID
    name: str
    actor_user_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RecordCycleCount:
    company_id: UUID
    session_id: UUID
    item_id: UUID
    counted_quantity: Decimal
    counted_at: datetime
    actor_user_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class InventoryItemRecord:
    id: UUID
    company_id: UUID
    code: str
    name: str
    stocking_unit: str
    allow_fractional: bool
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StockLocationRecord:
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
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class QuantityRecord:
    item_id: UUID
    location_id: UUID
    company_id: UUID
    branch_id: UUID
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StockMovementRecord:
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
    provenance_type: str | None
    provenance_id: UUID | None
    idempotency_key: str
    reversal_of_id: UUID | None
    unit_cost: Decimal | None
    currency: str | None
    valuation_method: str | None


@dataclass(frozen=True, slots=True)
class ReservationRecord:
    id: UUID
    company_id: UUID
    branch_id: UUID
    item_id: UUID
    location_id: UUID
    quantity: Decimal
    stocking_unit: str
    demand_type: str
    demand_id: UUID
    status: str
    expires_at: datetime | None
    idempotency_key: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdjustmentRecord:
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


@dataclass(frozen=True, slots=True)
class CycleCountEntryRecord:
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


@dataclass(frozen=True, slots=True)
class CycleCountSessionRecord:
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


class InventoryRepositoryContract(Protocol):
    async def create_item(
        self, session: AsyncSession, *, spec: CreateInventoryItem
    ) -> InventoryItemRecord: ...

    async def create_location(
        self, session: AsyncSession, *, spec: CreateStockLocation
    ) -> StockLocationRecord: ...

    async def post_movement(
        self, session: AsyncSession, *, spec: PostStockMovement
    ) -> StockMovementRecord: ...

    async def create_reservation(
        self, session: AsyncSession, *, spec: CreateReservation
    ) -> ReservationRecord: ...

    async def post_adjustment(
        self, session: AsyncSession, *, spec: PostInventoryAdjustment
    ) -> AdjustmentRecord: ...

    async def start_cycle_count(
        self, session: AsyncSession, *, spec: StartCycleCount
    ) -> CycleCountSessionRecord: ...

    async def record_cycle_count(
        self, session: AsyncSession, *, spec: RecordCycleCount
    ) -> CycleCountEntryRecord: ...

    async def complete_cycle_count(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        session_id: UUID,
        actor_user_id: UUID,
    ) -> CycleCountSessionRecord: ...

    async def reconcile_projection(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        item_id: UUID,
        location_id: UUID,
    ) -> QuantityRecord: ...
