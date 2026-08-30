from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.inventory.contracts import (
    AdjustmentRecord,
    AllocateReservation,
    AllocationRecord,
    CreateReservation,
    CreateStockLocation,
    CycleCountEntryRecord,
    CycleCountSessionRecord,
    PostInventoryAdjustment,
    PostStockMovement,
    RecordCycleCount,
    ReservationRecord,
    StartCycleCount,
    StockLocationRecord,
    StockMovementRecord,
    TransitionReservation,
)
from app.inventory.errors import InventoryValidation
from app.inventory.repository import InventoryRepository
from app.inventory.schemas import (
    AdjustmentCreate,
    CycleCountComplete,
    CycleCountRecord,
    CycleCountSessionResponse,
    CycleCountStart,
    InventoryOverview,
    ItemResponse,
    LocationCreate,
    LocationResponse,
    QuantityResponse,
    ReservationAllocate,
    ReservationCreate,
    ReservationRelease,
    ReservationResponse,
    TransferCreate,
)
from app.platform.permissions.authorization import AuthorizationContext


class InventoryService:
    def __init__(self, repository: InventoryRepository | None = None) -> None:
        self.repository = repository or InventoryRepository()

    @staticmethod
    def _branch(context: AuthorizationContext, branch_id: UUID) -> None:
        if not context.can_access_branch(branch_id):
            from app.inventory.errors import InventoryNotFound

            raise InventoryNotFound("Inventory branch was not found")

    async def overview(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None,
    ) -> InventoryOverview:
        branches = (
            tuple(context.authorized_branch_ids) if branch_id is None else (branch_id,)
        )
        if branch_id is not None:
            self._branch(context, branch_id)
        return InventoryOverview(
            items=tuple(
                ItemResponse.model_validate(record)
                for record in await self.repository.list_items(
                    session, company_id=context.company.id
                )
            ),
            locations=tuple(
                LocationResponse.model_validate(record)
                for record in await self.repository.list_locations(
                    session, company_id=context.company.id, branch_ids=branches
                )
            ),
            quantities=tuple(
                QuantityResponse.model_validate(record)
                for record in await self.repository.list_quantities(
                    session, company_id=context.company.id, branch_ids=branches
                )
            ),
            reservations=tuple(
                ReservationResponse.model_validate(record)
                for record in await self.repository.list_reservations(
                    session, company_id=context.company.id, branch_ids=branches
                )
            ),
        )

    async def create_location(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: LocationCreate,
    ) -> StockLocationRecord:
        self._branch(context, data.branch_id)
        async with session.begin():
            record = await self.repository.create_location(
                session,
                spec=CreateStockLocation(
                    company_id=context.company.id,
                    branch_id=data.branch_id,
                    code=data.code,
                    name=data.name,
                    location_type=data.location_type,
                    actor_user_id=context.user.id,
                    external_entity_type=data.external_entity_type,
                    external_entity_id=data.external_entity_id,
                ),
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_LOCATION_CREATED,
                "inventory_location",
                record.id,
                data.branch_id,
                {"code": record.code, "location_type": record.location_type},
            )
        return record

    async def transfer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: TransferCreate,
    ) -> StockMovementRecord:
        self._branch(context, data.branch_id)
        async with session.begin():
            record = await self.repository.post_movement(
                session,
                spec=PostStockMovement(
                    company_id=context.company.id,
                    branch_id=data.branch_id,
                    item_id=data.item_id,
                    movement_type="transfer",
                    quantity=data.quantity,
                    occurred_at=data.occurred_at,
                    actor_user_id=context.user.id,
                    idempotency_key=data.idempotency_key,
                    source_location_id=data.source_location_id,
                    destination_location_id=data.destination_location_id,
                ),
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_TRANSFER_POSTED,
                "inventory_movement",
                record.id,
                data.branch_id,
                {
                    "item_id": str(data.item_id),
                    "source_location_id": str(data.source_location_id),
                    "destination_location_id": str(data.destination_location_id),
                    "quantity": str(record.quantity),
                    "unit": record.stocking_unit,
                },
            )
        return record

    async def create_reservation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: ReservationCreate,
    ) -> ReservationRecord:
        self._branch(context, data.branch_id)
        async with session.begin():
            record = await self.repository.create_reservation(
                session,
                spec=CreateReservation(
                    company_id=context.company.id,
                    branch_id=data.branch_id,
                    item_id=data.item_id,
                    location_id=data.location_id,
                    quantity=data.quantity,
                    demand_type=data.demand_type,
                    demand_id=data.demand_id,
                    actor_user_id=context.user.id,
                    idempotency_key=data.idempotency_key,
                    expires_at=data.expires_at,
                ),
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_RESERVATION_CREATED,
                "inventory_reservation",
                record.id,
                data.branch_id,
                {
                    "item_id": str(data.item_id),
                    "location_id": str(data.location_id),
                    "quantity": str(record.quantity),
                    "unit": record.stocking_unit,
                    "demand_type": record.demand_type,
                    "demand_id": str(record.demand_id),
                },
            )
        return record

    async def allocate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        reservation_id: UUID,
        data: ReservationAllocate,
    ) -> AllocationRecord:
        async with session.begin():
            reservation = await self._reservation(session, context, reservation_id)
            return await self.repository.allocate_reservation(
                session,
                spec=AllocateReservation(
                    company_id=context.company.id,
                    branch_id=reservation.branch_id,
                    reservation_id=reservation.id,
                    item_id=reservation.item_id,
                    location_id=reservation.location_id,
                    actor_user_id=context.user.id,
                    authorized_branch_ids=tuple(context.authorized_branch_ids),
                    expected_version=data.expected_version,
                    idempotency_key=data.idempotency_key,
                    quantity=data.quantity,
                    allow_partial=data.allow_partial,
                ),
            )

    async def release(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        reservation_id: UUID,
        data: ReservationRelease,
    ) -> ReservationRecord:
        async with session.begin():
            reservation = await self._reservation(session, context, reservation_id)
            record = await self.repository.transition_reservation(
                session,
                spec=TransitionReservation(
                    company_id=context.company.id,
                    branch_id=reservation.branch_id,
                    reservation_id=reservation.id,
                    actor_user_id=context.user.id,
                    authorized_branch_ids=tuple(context.authorized_branch_ids),
                    expected_version=data.expected_version,
                    target_status="released",
                    idempotency_key=data.idempotency_key,
                ),
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_RESERVATION_RELEASED,
                "inventory_reservation",
                record.id,
                record.branch_id,
                {
                    "item_id": str(record.item_id),
                    "location_id": str(record.location_id),
                    "version": record.version,
                },
            )
        return record

    async def post_adjustment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: AdjustmentCreate,
    ) -> AdjustmentRecord:
        self._branch(context, data.branch_id)
        async with session.begin():
            record = await self.repository.post_adjustment(
                session,
                spec=PostInventoryAdjustment(
                    company_id=context.company.id,
                    branch_id=data.branch_id,
                    item_id=data.item_id,
                    location_id=data.location_id,
                    reason=data.reason,
                    quantity_delta=data.quantity_delta,
                    note=data.note,
                    occurred_at=data.occurred_at,
                    actor_user_id=context.user.id,
                    idempotency_key=data.idempotency_key,
                ),
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_ADJUSTMENT_POSTED,
                "inventory_adjustment",
                record.id,
                record.branch_id,
                {
                    "item_id": str(record.item_id),
                    "location_id": str(record.location_id),
                    "reason": record.reason,
                    "quantity_delta": str(record.quantity_delta),
                    "movement_id": str(record.movement_id),
                },
            )
        return record

    async def list_cycle_counts(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[CycleCountSessionResponse, ...]:
        if not 1 <= limit <= 200 or offset < 0:
            raise InventoryValidation("Cycle-count pagination is invalid")
        branches = (
            tuple(context.authorized_branch_ids) if branch_id is None else (branch_id,)
        )
        if branch_id is not None:
            self._branch(context, branch_id)
        rows = await self.repository.list_cycle_counts(
            session,
            company_id=context.company.id,
            branch_ids=branches,
            limit=limit,
            offset=offset,
        )
        return tuple(
            CycleCountSessionResponse.model_validate(cycle).model_copy(
                update={"entries": tuple(entries)}
            )
            for cycle, entries in rows
        )

    async def start_cycle_count(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: CycleCountStart,
    ) -> CycleCountSessionRecord:
        self._branch(context, data.branch_id)
        async with session.begin():
            record = await self.repository.start_cycle_count(
                session,
                spec=StartCycleCount(
                    company_id=context.company.id,
                    branch_id=data.branch_id,
                    location_id=data.location_id,
                    name=data.name,
                    actor_user_id=context.user.id,
                    idempotency_key=data.idempotency_key,
                ),
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_CYCLE_COUNT_STARTED,
                "inventory_cycle_count",
                record.id,
                record.branch_id,
                {"location_id": str(record.location_id), "version": record.version},
            )
        return record

    async def record_cycle_count(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        session_id: UUID,
        data: CycleCountRecord,
    ) -> CycleCountEntryRecord:
        cycle = await self.repository.get_cycle_count(
            session, company_id=context.company.id, session_id=session_id
        )
        if cycle is None or not context.can_access_branch(cycle.branch_id):
            from app.inventory.errors import InventoryNotFound

            raise InventoryNotFound("Cycle count was not found")
        await session.rollback()
        async with session.begin():
            record = await self.repository.record_cycle_count(
                session,
                spec=RecordCycleCount(
                    company_id=context.company.id,
                    session_id=session_id,
                    item_id=data.item_id,
                    counted_quantity=data.counted_quantity,
                    counted_at=data.counted_at,
                    actor_user_id=context.user.id,
                    idempotency_key=data.idempotency_key,
                ),
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_CYCLE_COUNT_RECORDED,
                "inventory_cycle_count_entry",
                record.id,
                cycle.branch_id,
                {
                    "session_id": str(record.session_id),
                    "item_id": str(record.item_id),
                    "variance": str(record.variance),
                },
            )
        return record

    async def complete_cycle_count(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        session_id: UUID,
        data: CycleCountComplete,
    ) -> CycleCountSessionRecord:
        cycle = await self.repository.get_cycle_count(
            session, company_id=context.company.id, session_id=session_id
        )
        if cycle is None or not context.can_access_branch(cycle.branch_id):
            from app.inventory.errors import InventoryNotFound

            raise InventoryNotFound("Cycle count was not found")
        await session.rollback()
        async with session.begin():
            record = await self.repository.complete_cycle_count(
                session,
                company_id=context.company.id,
                session_id=session_id,
                actor_user_id=context.user.id,
                expected_version=data.expected_version,
            )
            await self._event(
                session,
                context,
                EventType.INVENTORY_CYCLE_COUNT_COMPLETED,
                "inventory_cycle_count",
                record.id,
                record.branch_id,
                {"location_id": str(record.location_id), "version": record.version},
            )
        return record

    async def _reservation(
        self, session: AsyncSession, context: AuthorizationContext, reservation_id: UUID
    ) -> ReservationRecord:
        from app.inventory.errors import InventoryNotFound

        for branch_id in context.authorized_branch_ids:
            record = await self.repository.get_reservation(
                session,
                company_id=context.company.id,
                branch_id=branch_id,
                reservation_id=reservation_id,
            )
            if record is not None:
                return record
        raise InventoryNotFound("Reservation was not found")

    @staticmethod
    async def _event(
        session: AsyncSession,
        context: AuthorizationContext,
        event_type: EventType,
        entity_type: str,
        entity_id: UUID,
        branch_id: UUID,
        payload: dict[str, object],
    ) -> None:
        existing = await session.scalar(
            select(BusinessEvent.id).where(
                BusinessEvent.company_id == context.company.id,
                BusinessEvent.event_type == event_type.value,
                BusinessEvent.entity_type == entity_type,
                BusinessEvent.entity_id == entity_id,
            )
        )
        if existing is not None:
            return
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=branch_id,
                user_id=context.user.id,
                payload=payload,
            ),
        )


inventory_service = InventoryService()
