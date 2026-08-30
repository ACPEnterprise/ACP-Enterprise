from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.contracts import (
    AdjustmentRecord,
    AllocateReservation,
    AllocationRecord,
    CreateInventoryItem,
    CreateReservation,
    CreateStockLocation,
    CycleCountEntryRecord,
    CycleCountSessionRecord,
    InventoryItemRecord,
    MaterialIssueRecord,
    PostInventoryAdjustment,
    PostMaterialIssue,
    PostStockMovement,
    QuantityRecord,
    RecordCycleCount,
    ReservationRecord,
    ReverseMaterialIssue,
    StartCycleCount,
    StockLocationRecord,
    StockMovementRecord,
    TransitionReservation,
)
from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.models import (
    CycleCountEntry,
    CycleCountSession,
    InventoryAdjustment,
    InventoryItem,
    InventoryQuantity,
    InventoryReservation,
    MaterialIssue,
    ReservationAllocation,
    ReservationLifecycleEvent,
    StockLocation,
    StockMovement,
)


class InventoryRepository:
    """Company- and Branch-scoped persistence for authoritative Inventory facts."""

    async def create_item(
        self, session: AsyncSession, *, spec: CreateInventoryItem
    ) -> InventoryItemRecord:
        code = spec.code.strip().upper()
        name = spec.name.strip()
        unit = spec.stocking_unit.strip()
        if not code or not name or not unit:
            raise InventoryValidation("Item code, name, and stocking unit are required")
        item = InventoryItem(
            company_id=spec.company_id,
            code=code,
            name=name,
            stocking_unit=unit,
            allow_fractional=spec.allow_fractional,
            status="active",
            version=1,
            created_by_user_id=spec.actor_user_id,
            updated_by_user_id=spec.actor_user_id,
        )
        session.add(item)
        await session.flush()
        return self._item_record(item)

    async def list_items(
        self, session: AsyncSession, *, company_id: UUID
    ) -> tuple[InventoryItemRecord, ...]:
        rows = await session.scalars(
            select(InventoryItem)
            .where(InventoryItem.company_id == company_id)
            .order_by(InventoryItem.code, InventoryItem.id)
        )
        return tuple(self._item_record(row) for row in rows.all())

    async def get_item(
        self, session: AsyncSession, *, company_id: UUID, item_id: UUID
    ) -> InventoryItemRecord | None:
        item = await session.scalar(
            select(InventoryItem).where(
                InventoryItem.company_id == company_id, InventoryItem.id == item_id
            )
        )
        return self._item_record(item) if item else None

    async def create_location(
        self, session: AsyncSession, *, spec: CreateStockLocation
    ) -> StockLocationRecord:
        code = spec.code.strip().upper()
        name = spec.name.strip()
        if not code or not name:
            raise InventoryValidation("Location code and name are required")
        if (spec.external_entity_type is None) != (spec.external_entity_id is None):
            raise InventoryValidation("External location references must be complete")
        location = StockLocation(
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            code=code,
            name=name,
            location_type=spec.location_type,
            status="active",
            external_entity_type=spec.external_entity_type,
            external_entity_id=spec.external_entity_id,
            version=1,
            created_by_user_id=spec.actor_user_id,
            updated_by_user_id=spec.actor_user_id,
        )
        session.add(location)
        await session.flush()
        return self._location_record(location)

    async def get_location(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        location_id: UUID,
    ) -> StockLocationRecord | None:
        location = await session.scalar(
            select(StockLocation).where(
                StockLocation.company_id == company_id,
                StockLocation.branch_id == branch_id,
                StockLocation.id == location_id,
            )
        )
        return self._location_record(location) if location else None

    async def list_locations(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_ids: tuple[UUID, ...],
    ) -> tuple[StockLocationRecord, ...]:
        if not branch_ids:
            return ()
        rows = await session.scalars(
            select(StockLocation)
            .where(
                StockLocation.company_id == company_id,
                StockLocation.branch_id.in_(branch_ids),
            )
            .order_by(StockLocation.branch_id, StockLocation.code, StockLocation.id)
        )
        return tuple(self._location_record(row) for row in rows.all())

    async def post_movement(
        self, session: AsyncSession, *, spec: PostStockMovement
    ) -> StockMovementRecord:
        key = spec.idempotency_key.strip()
        if not key:
            raise InventoryValidation("Movement idempotency key is required")
        await self._lock_idempotency(
            session, spec.company_id, "movement", key
        )
        existing = await session.scalar(
            select(StockMovement).where(
                StockMovement.company_id == spec.company_id,
                StockMovement.idempotency_key == key,
            )
        )
        if existing:
            self._assert_same_movement(existing, spec)
            return self._movement_record(existing)
        item = await self._active_item(
            session, company_id=spec.company_id, item_id=spec.item_id
        )
        self._validate_quantity(item, spec.quantity)
        self._validate_movement_shape(spec)
        if spec.source_location_id:
            await self._active_location(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                location_id=spec.source_location_id,
            )
        if spec.destination_location_id:
            await self._active_location(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                location_id=spec.destination_location_id,
            )
        if spec.source_location_id:
            source = await self._locked_quantity(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                item_id=spec.item_id,
                location_id=spec.source_location_id,
            )
            authoritative = await self._authoritative_on_hand(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                item_id=spec.item_id,
                location_id=spec.source_location_id,
            )
            if authoritative - spec.quantity < source.reserved:
                raise InventoryConflict(
                    "Movement would make available quantity negative"
                )
        movement = StockMovement(
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            item_id=spec.item_id,
            movement_type=spec.movement_type,
            source_location_id=spec.source_location_id,
            destination_location_id=spec.destination_location_id,
            quantity=spec.quantity,
            stocking_unit=item.stocking_unit,
            occurred_at=spec.occurred_at,
            actor_user_id=spec.actor_user_id,
            provenance_type=spec.provenance_type,
            provenance_id=spec.provenance_id,
            idempotency_key=key,
            reversal_of_id=spec.reversal_of_id,
            unit_cost=spec.unit_cost,
            currency=spec.currency,
            valuation_method=spec.valuation_method,
        )
        session.add(movement)
        await session.flush()
        affected_locations = (
            location_id
            for location_id in (
                spec.source_location_id,
                spec.destination_location_id,
            )
            if location_id is not None
        )
        for location_id in affected_locations:
            await self._reconcile_quantity(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                item_id=spec.item_id,
                location_id=location_id,
            )
        return self._movement_record(movement)

    async def reconcile_projection(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        item_id: UUID,
        location_id: UUID,
    ) -> QuantityRecord:
        await self._active_item(session, company_id=company_id, item_id=item_id)
        await self._active_location(
            session,
            company_id=company_id,
            branch_id=branch_id,
            location_id=location_id,
        )
        quantity = await self._reconcile_quantity(
            session,
            company_id=company_id,
            branch_id=branch_id,
            item_id=item_id,
            location_id=location_id,
        )
        return self._quantity_record(quantity)

    async def post_adjustment(
        self, session: AsyncSession, *, spec: PostInventoryAdjustment
    ) -> AdjustmentRecord:
        key = spec.idempotency_key.strip()
        if not key:
            raise InventoryValidation("Adjustment idempotency key is required")
        await self._lock_idempotency(session, spec.company_id, "adjustment", key)
        existing = await session.scalar(
            select(InventoryAdjustment).where(
                InventoryAdjustment.company_id == spec.company_id,
                InventoryAdjustment.idempotency_key == key,
            )
        )
        if existing:
            self._assert_same_adjustment(existing, spec)
            return self._adjustment_record(existing)
        reason = spec.reason.strip().lower()
        note = spec.note.strip()
        if reason not in {"gain", "loss", "damaged", "expired", "found"}:
            raise InventoryValidation("Unsupported adjustment reason")
        if not note or not key:
            raise InventoryValidation(
                "Adjustment note and idempotency key are required"
            )
        if spec.quantity_delta == 0:
            raise InventoryValidation("Adjustment quantity delta cannot be zero")
        inbound = reason in {"gain", "found"}
        if inbound != (spec.quantity_delta > 0):
            raise InventoryValidation(
                "Adjustment reason and quantity direction conflict"
            )
        item = await self._active_item(
            session, company_id=spec.company_id, item_id=spec.item_id
        )
        self._validate_quantity(item, abs(spec.quantity_delta))
        adjustment = InventoryAdjustment(
            id=uuid4(),
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
            reason=reason,
            quantity_delta=spec.quantity_delta,
            stocking_unit=item.stocking_unit,
            note=note,
            occurred_at=spec.occurred_at,
            actor_user_id=spec.actor_user_id,
            idempotency_key=key,
            movement_id=UUID(int=0),
            cycle_count_entry_id=spec.cycle_count_entry_id,
        )
        movement = await self.post_movement(
            session,
            spec=PostStockMovement(
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                item_id=spec.item_id,
                movement_type="adjustment_in" if inbound else "adjustment_out",
                quantity=abs(spec.quantity_delta),
                occurred_at=spec.occurred_at,
                actor_user_id=spec.actor_user_id,
                idempotency_key=f"adjustment:{key}",
                source_location_id=None if inbound else spec.location_id,
                destination_location_id=spec.location_id if inbound else None,
                provenance_type="inventory_adjustment",
                provenance_id=adjustment.id,
            ),
        )
        adjustment.movement_id = movement.id
        session.add(adjustment)
        await session.flush()
        return self._adjustment_record(adjustment)

    async def start_cycle_count(
        self, session: AsyncSession, *, spec: StartCycleCount
    ) -> CycleCountSessionRecord:
        key = spec.idempotency_key.strip()
        if not key or not spec.name.strip():
            raise InventoryValidation(
                "Cycle count name and idempotency key are required"
            )
        await self._lock_idempotency(session, spec.company_id, "cycle-start", key)
        existing = await session.scalar(
            select(CycleCountSession).where(
                CycleCountSession.company_id == spec.company_id,
                CycleCountSession.idempotency_key == key,
            )
        )
        if existing:
            if (
                existing.branch_id,
                existing.location_id,
                existing.name,
                existing.started_by_user_id,
            ) != (
                spec.branch_id,
                spec.location_id,
                spec.name.strip(),
                spec.actor_user_id,
            ):
                raise InventoryConflict("Cycle count idempotency key was reused")
            return self._cycle_session_record(existing)
        await self._active_location(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            location_id=spec.location_id,
        )
        cycle = CycleCountSession(
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            location_id=spec.location_id,
            name=spec.name.strip(),
            status="open",
            idempotency_key=key,
            version=1,
            started_by_user_id=spec.actor_user_id,
        )
        session.add(cycle)
        await session.flush()
        return self._cycle_session_record(cycle)

    async def list_cycle_counts(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_ids: tuple[UUID, ...],
        limit: int,
        offset: int,
    ) -> tuple[tuple[CycleCountSessionRecord, tuple[CycleCountEntryRecord, ...]], ...]:
        cycles = tuple(
            (
                await session.scalars(
                    select(CycleCountSession)
                    .where(
                        CycleCountSession.company_id == company_id,
                        CycleCountSession.branch_id.in_(branch_ids),
                    )
                    .order_by(CycleCountSession.started_at.desc(), CycleCountSession.id)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )
        cycle_ids = tuple(row.id for row in cycles)
        entries = (
            tuple(
                (
                    await session.scalars(
                        select(CycleCountEntry)
                        .where(
                            CycleCountEntry.company_id == company_id,
                            CycleCountEntry.session_id.in_(cycle_ids),
                        )
                        .order_by(CycleCountEntry.counted_at, CycleCountEntry.id)
                    )
                ).all()
            )
            if cycle_ids
            else ()
        )
        return tuple(
            (
                self._cycle_session_record(cycle),
                tuple(
                    self._cycle_entry_record(entry)
                    for entry in entries
                    if entry.session_id == cycle.id
                ),
            )
            for cycle in cycles
        )

    async def get_cycle_count(
        self, session: AsyncSession, *, company_id: UUID, session_id: UUID
    ) -> CycleCountSessionRecord | None:
        cycle = await session.scalar(
            select(CycleCountSession).where(
                CycleCountSession.company_id == company_id,
                CycleCountSession.id == session_id,
            )
        )
        return self._cycle_session_record(cycle) if cycle else None

    async def record_cycle_count(
        self, session: AsyncSession, *, spec: RecordCycleCount
    ) -> CycleCountEntryRecord:
        key = spec.idempotency_key.strip()
        if not key:
            raise InventoryValidation("Cycle count entry idempotency key is required")
        await self._lock_idempotency(session, spec.company_id, "cycle-entry", key)
        existing = await session.scalar(
            select(CycleCountEntry).where(
                CycleCountEntry.company_id == spec.company_id,
                CycleCountEntry.idempotency_key == key,
            )
        )
        if existing:
            if (
                existing.session_id,
                existing.item_id,
                existing.counted_quantity,
                existing.counted_at,
                existing.counted_by_user_id,
            ) != (
                spec.session_id,
                spec.item_id,
                spec.counted_quantity,
                spec.counted_at,
                spec.actor_user_id,
            ):
                raise InventoryConflict("Cycle count entry idempotency key was reused")
            return self._cycle_entry_record(existing)
        cycle = await self._locked_cycle(session, spec.company_id, spec.session_id)
        if cycle.status != "open":
            raise InventoryConflict("Completed cycle count cannot accept entries")
        item = await self._active_item(
            session, company_id=spec.company_id, item_id=spec.item_id
        )
        if spec.counted_quantity < 0:
            raise InventoryValidation("Counted quantity cannot be negative")
        if (
            not item.allow_fractional
            and spec.counted_quantity != spec.counted_quantity.to_integral_value()
        ):
            raise InventoryValidation("Item does not allow fractional quantity")
        expected = await self._authoritative_on_hand(
            session,
            company_id=spec.company_id,
            branch_id=cycle.branch_id,
            item_id=spec.item_id,
            location_id=cycle.location_id,
        )
        entry = CycleCountEntry(
            company_id=spec.company_id,
            session_id=cycle.id,
            item_id=spec.item_id,
            expected_quantity=expected,
            counted_quantity=spec.counted_quantity,
            stocking_unit=item.stocking_unit,
            counted_at=spec.counted_at,
            counted_by_user_id=spec.actor_user_id,
            idempotency_key=key,
        )
        session.add(entry)
        await session.flush()
        return self._cycle_entry_record(entry)

    async def complete_cycle_count(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        session_id: UUID,
        actor_user_id: UUID,
        expected_version: int | None = None,
    ) -> CycleCountSessionRecord:
        cycle = await self._locked_cycle(session, company_id, session_id)
        if cycle.status == "completed":
            return self._cycle_session_record(cycle)
        if expected_version is not None and cycle.version != expected_version:
            raise InventoryConflict("Cycle count version changed")
        entries = (
            await session.scalars(
                select(CycleCountEntry)
                .where(
                    CycleCountEntry.company_id == company_id,
                    CycleCountEntry.session_id == session_id,
                )
                .order_by(CycleCountEntry.id)
            )
        ).all()
        if not entries:
            raise InventoryConflict("Cycle count requires at least one entry")
        for entry in entries:
            delta = entry.counted_quantity - entry.expected_quantity
            if delta:
                await self.post_adjustment(
                    session,
                    spec=PostInventoryAdjustment(
                        company_id=company_id,
                        branch_id=cycle.branch_id,
                        item_id=entry.item_id,
                        location_id=cycle.location_id,
                        reason="gain" if delta > 0 else "loss",
                        quantity_delta=delta,
                        note=f"Cycle count variance: {cycle.name}",
                        occurred_at=entry.counted_at,
                        actor_user_id=actor_user_id,
                        idempotency_key=f"cycle:{cycle.id}:{entry.id}",
                        cycle_count_entry_id=entry.id,
                    ),
                )
        cycle.status = "completed"
        cycle.version += 1
        cycle.completed_by_user_id = actor_user_id
        cycle.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return self._cycle_session_record(cycle)

    async def get_quantity(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        item_id: UUID,
        location_id: UUID,
    ) -> QuantityRecord:
        quantity = await session.scalar(
            select(InventoryQuantity).where(
                InventoryQuantity.company_id == company_id,
                InventoryQuantity.branch_id == branch_id,
                InventoryQuantity.item_id == item_id,
                InventoryQuantity.location_id == location_id,
            )
        )
        if quantity is None:
            return QuantityRecord(
                item_id=item_id,
                location_id=location_id,
                company_id=company_id,
                branch_id=branch_id,
                on_hand=Decimal(0),
                reserved=Decimal(0),
                available=Decimal(0),
                version=0,
                updated_at=datetime.now(timezone.utc),
            )
        return self._quantity_record(quantity)

    async def list_quantities(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_ids: tuple[UUID, ...],
    ) -> tuple[QuantityRecord, ...]:
        if not branch_ids:
            return ()
        rows = await session.scalars(
            select(InventoryQuantity)
            .where(
                InventoryQuantity.company_id == company_id,
                InventoryQuantity.branch_id.in_(branch_ids),
            )
            .order_by(
                InventoryQuantity.branch_id,
                InventoryQuantity.location_id,
                InventoryQuantity.item_id,
            )
        )
        return tuple(self._quantity_record(row) for row in rows.all())

    async def list_movements(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        item_id: UUID,
    ) -> tuple[StockMovementRecord, ...]:
        rows = await session.scalars(
            select(StockMovement)
            .where(
                StockMovement.company_id == company_id,
                StockMovement.item_id == item_id,
            )
            .order_by(StockMovement.occurred_at, StockMovement.id)
        )
        return tuple(self._movement_record(row) for row in rows.all())

    async def create_reservation(
        self, session: AsyncSession, *, spec: CreateReservation
    ) -> ReservationRecord:
        key = spec.idempotency_key.strip()
        if not key:
            raise InventoryValidation("Reservation idempotency key is required")
        await self._lock_idempotency(
            session, spec.company_id, "reservation", key
        )
        existing = await session.scalar(
            select(InventoryReservation).where(
                InventoryReservation.company_id == spec.company_id,
                InventoryReservation.idempotency_key == key,
            )
        )
        if existing:
            self._assert_same_reservation(existing, spec)
            return self._reservation_record(existing)
        item = await self._active_item(
            session, company_id=spec.company_id, item_id=spec.item_id
        )
        self._validate_quantity(item, spec.quantity)
        await self._active_location(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            location_id=spec.location_id,
        )
        reservation = InventoryReservation(
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
            quantity=spec.quantity,
            allocated_quantity=Decimal(0),
            issued_quantity=Decimal(0),
            stocking_unit=item.stocking_unit,
            demand_type=spec.demand_type.strip(),
            demand_id=spec.demand_id,
            status="requested",
            expires_at=spec.expires_at,
            idempotency_key=key,
            version=1,
            created_by_user_id=spec.actor_user_id,
            updated_by_user_id=spec.actor_user_id,
        )
        session.add(reservation)
        await session.flush()
        return self._reservation_record(reservation)

    async def get_reservation(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        reservation_id: UUID,
    ) -> ReservationRecord | None:
        reservation = await session.scalar(
            select(InventoryReservation).where(
                InventoryReservation.company_id == company_id,
                InventoryReservation.branch_id == branch_id,
                InventoryReservation.id == reservation_id,
            )
        )
        return self._reservation_record(reservation) if reservation else None

    async def list_reservations(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_ids: tuple[UUID, ...],
    ) -> tuple[ReservationRecord, ...]:
        if not branch_ids:
            return ()
        rows = await session.scalars(
            select(InventoryReservation)
            .where(
                InventoryReservation.company_id == company_id,
                InventoryReservation.branch_id.in_(branch_ids),
            )
            .order_by(InventoryReservation.created_at.desc(), InventoryReservation.id)
        )
        return tuple(self._reservation_record(row) for row in rows.all())

    async def allocate_reservation(
        self, session: AsyncSession, *, spec: AllocateReservation
    ) -> AllocationRecord:
        key = spec.idempotency_key.strip()
        self._authorize_branch(spec.branch_id, spec.authorized_branch_ids)
        existing = await session.scalar(
            select(ReservationAllocation).where(
                ReservationAllocation.company_id == spec.company_id,
                ReservationAllocation.idempotency_key == key,
            )
        )
        if existing:
            self._assert_same_allocation(existing, spec)
            return self._allocation_record(existing)
        if not key:
            raise InventoryValidation("Allocation idempotency key is required")
        reservation = await self._locked_reservation(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            reservation_id=spec.reservation_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
        )
        concurrent_replay = await session.scalar(
            select(ReservationAllocation).where(
                ReservationAllocation.company_id == spec.company_id,
                ReservationAllocation.idempotency_key == key,
            )
        )
        if concurrent_replay:
            self._assert_same_allocation(concurrent_replay, spec)
            return self._allocation_record(concurrent_replay)
        self._assert_version(reservation.version, spec.expected_version)
        if reservation.status not in {"requested", "partially_allocated"}:
            raise InventoryConflict("Reservation is not available for allocation")
        remaining = reservation.quantity - reservation.allocated_quantity
        requested = remaining if spec.quantity is None else spec.quantity
        if requested <= 0 or requested > remaining:
            raise InventoryValidation(
                "Allocation quantity exceeds reservation remainder"
            )
        if requested < remaining and not spec.allow_partial:
            raise InventoryValidation("Partial allocation was not explicitly allowed")
        quantity = await self._locked_quantity(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
        )
        available = quantity.on_hand - quantity.reserved
        allocated = min(requested, available) if spec.allow_partial else requested
        if allocated <= 0 or (not spec.allow_partial and available < requested):
            raise InventoryConflict("Insufficient available quantity for allocation")
        old_status = reservation.status
        old_version = reservation.version
        reservation.allocated_quantity += allocated
        reservation.status = (
            "allocated"
            if reservation.allocated_quantity == reservation.quantity
            else "partially_allocated"
        )
        reservation.version += 1
        reservation.updated_by_user_id = spec.actor_user_id
        reservation.updated_at = datetime.now(timezone.utc)
        quantity.reserved += allocated
        quantity.version += 1
        quantity.updated_at = datetime.now(timezone.utc)
        allocation = ReservationAllocation(
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            reservation_id=spec.reservation_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
            quantity=allocated,
            requested_quantity=requested,
            partial_allowed=spec.allow_partial,
            stocking_unit=reservation.stocking_unit,
            reservation_version=old_version,
            idempotency_key=key,
            allocated_by_user_id=spec.actor_user_id,
        )
        session.add(allocation)
        if old_status != reservation.status:
            self._add_lifecycle_event(
                session,
                reservation=reservation,
                from_status=old_status,
                from_version=old_version,
                to_status=reservation.status,
                actor_user_id=spec.actor_user_id,
                idempotency_key=f"allocation:{key}",
            )
        await session.flush()
        return self._allocation_record(allocation)

    async def list_allocations(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        reservation_id: UUID,
    ) -> tuple[AllocationRecord, ...]:
        rows = await session.scalars(
            select(ReservationAllocation)
            .where(
                ReservationAllocation.company_id == company_id,
                ReservationAllocation.branch_id == branch_id,
                ReservationAllocation.reservation_id == reservation_id,
            )
            .order_by(ReservationAllocation.allocated_at, ReservationAllocation.id)
        )
        return tuple(self._allocation_record(row) for row in rows.all())

    async def transition_reservation(
        self, session: AsyncSession, *, spec: TransitionReservation
    ) -> ReservationRecord:
        key = spec.idempotency_key.strip()
        self._authorize_branch(spec.branch_id, spec.authorized_branch_ids)
        existing = await session.scalar(
            select(ReservationLifecycleEvent).where(
                ReservationLifecycleEvent.company_id == spec.company_id,
                ReservationLifecycleEvent.idempotency_key == f"transition:{key}",
            )
        )
        if existing:
            if (
                existing.reservation_id != spec.reservation_id
                or existing.to_status != spec.target_status
                or existing.actor_user_id != spec.actor_user_id
            ):
                raise InventoryConflict(
                    "Reservation transition idempotency key was reused"
                )
            reservation = await self._locked_reservation(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                reservation_id=spec.reservation_id,
            )
            return self._reservation_record(reservation)
        if spec.target_status not in {"released", "cancelled"}:
            raise InventoryValidation("Unsupported explicit reservation transition")
        if not key:
            raise InventoryValidation("Transition idempotency key is required")
        reservation = await self._locked_reservation(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            reservation_id=spec.reservation_id,
        )
        concurrent_replay = await session.scalar(
            select(ReservationLifecycleEvent).where(
                ReservationLifecycleEvent.company_id == spec.company_id,
                ReservationLifecycleEvent.idempotency_key == f"transition:{key}",
            )
        )
        if concurrent_replay:
            if concurrent_replay.to_status != spec.target_status:
                raise InventoryConflict(
                    "Reservation transition idempotency key was reused"
                )
            return self._reservation_record(reservation)
        self._assert_version(reservation.version, spec.expected_version)
        if reservation.status not in {"requested", "partially_allocated", "allocated"}:
            raise InventoryConflict(
                "Reservation transition is not valid from current state"
            )
        old_status = reservation.status
        old_version = reservation.version
        outstanding = reservation.allocated_quantity - reservation.issued_quantity
        if outstanding:
            quantity = await self._locked_quantity(
                session,
                company_id=reservation.company_id,
                branch_id=reservation.branch_id,
                item_id=reservation.item_id,
                location_id=reservation.location_id,
            )
            quantity.reserved -= outstanding
            quantity.version += 1
            quantity.updated_at = datetime.now(timezone.utc)
        reservation.status = spec.target_status
        reservation.version += 1
        reservation.updated_by_user_id = spec.actor_user_id
        reservation.updated_at = datetime.now(timezone.utc)
        self._add_lifecycle_event(
            session,
            reservation=reservation,
            from_status=old_status,
            from_version=old_version,
            to_status=spec.target_status,
            actor_user_id=spec.actor_user_id,
            idempotency_key=f"transition:{key}",
        )
        await session.flush()
        return self._reservation_record(reservation)

    async def post_material_issue(
        self, session: AsyncSession, *, spec: PostMaterialIssue
    ) -> MaterialIssueRecord:
        key = spec.idempotency_key.strip()
        self._authorize_branch(spec.branch_id, spec.authorized_branch_ids)
        existing = await session.scalar(
            select(MaterialIssue).where(
                MaterialIssue.company_id == spec.company_id,
                MaterialIssue.idempotency_key == key,
            )
        )
        if existing:
            self._assert_same_issue(existing, spec)
            return self._issue_record(existing)
        self._validate_external_reference(
            spec.external_reference_type, spec.external_reference_id
        )
        if not key:
            raise InventoryValidation("Material issue idempotency key is required")
        reservation = await self._locked_reservation(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            reservation_id=spec.reservation_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
        )
        concurrent_replay = await session.scalar(
            select(MaterialIssue).where(
                MaterialIssue.company_id == spec.company_id,
                MaterialIssue.idempotency_key == key,
            )
        )
        if concurrent_replay:
            self._assert_same_issue(concurrent_replay, spec)
            return self._issue_record(concurrent_replay)
        self._assert_version(reservation.version, spec.expected_reservation_version)
        if reservation.status != "allocated":
            raise InventoryConflict("Only allocated reservations can be issued")
        allocation = await self._scoped_allocation(session, spec)
        prior = await session.scalar(
            select(MaterialIssue).where(
                MaterialIssue.company_id == spec.company_id,
                MaterialIssue.allocation_id == spec.allocation_id,
                MaterialIssue.issue_type == "issue",
            )
        )
        if prior:
            raise InventoryConflict("Allocation already has material issue evidence")
        quantity = await self._locked_quantity(
            session,
            company_id=reservation.company_id,
            branch_id=reservation.branch_id,
            item_id=reservation.item_id,
            location_id=reservation.location_id,
        )
        if quantity.reserved < allocation.quantity:
            raise InventoryConflict("Reservation projection is inconsistent")
        issue = MaterialIssue(
            id=uuid4(),
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            reservation_id=spec.reservation_id,
            allocation_id=spec.allocation_id,
            issue_type="issue",
            item_id=spec.item_id,
            location_id=spec.location_id,
            quantity=allocation.quantity,
            stocking_unit=allocation.stocking_unit,
            occurred_at=spec.occurred_at,
            actor_user_id=spec.actor_user_id,
            idempotency_key=key,
            movement_id=UUID(int=0),
            external_reference_type=spec.external_reference_type,
            external_reference_id=spec.external_reference_id,
        )
        quantity.reserved -= allocation.quantity
        quantity.version += 1
        quantity.updated_at = datetime.now(timezone.utc)
        movement = await self.post_movement(
            session,
            spec=PostStockMovement(
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                item_id=spec.item_id,
                movement_type="material_issue",
                quantity=allocation.quantity,
                occurred_at=spec.occurred_at,
                actor_user_id=spec.actor_user_id,
                idempotency_key=f"material-issue:{key}",
                source_location_id=spec.location_id,
                provenance_type="material_issue",
                provenance_id=issue.id,
            ),
        )
        issue.movement_id = movement.id
        session.add(issue)
        old_status = reservation.status
        old_version = reservation.version
        reservation.issued_quantity += allocation.quantity
        if reservation.issued_quantity == reservation.quantity:
            reservation.status = "fulfilled"
        reservation.version += 1
        reservation.updated_by_user_id = spec.actor_user_id
        reservation.updated_at = datetime.now(timezone.utc)
        if old_status != reservation.status:
            self._add_lifecycle_event(
                session,
                reservation=reservation,
                from_status=old_status,
                from_version=old_version,
                to_status=reservation.status,
                actor_user_id=spec.actor_user_id,
                idempotency_key=f"issue:{key}",
            )
        await session.flush()
        return self._issue_record(issue)

    async def reverse_material_issue(
        self, session: AsyncSession, *, spec: ReverseMaterialIssue
    ) -> MaterialIssueRecord:
        key = spec.idempotency_key.strip()
        self._authorize_branch(spec.branch_id, spec.authorized_branch_ids)
        existing = await session.scalar(
            select(MaterialIssue).where(
                MaterialIssue.company_id == spec.company_id,
                MaterialIssue.idempotency_key == key,
            )
        )
        if existing:
            if (
                existing.issue_type != "reversal"
                or existing.reversal_of_issue_id != spec.issue_id
                or existing.actor_user_id != spec.actor_user_id
                or existing.occurred_at != spec.occurred_at
            ):
                raise InventoryConflict("Issue reversal idempotency key was reused")
            return self._issue_record(existing)
        original = await session.scalar(
            select(MaterialIssue).where(
                MaterialIssue.company_id == spec.company_id,
                MaterialIssue.branch_id == spec.branch_id,
                MaterialIssue.id == spec.issue_id,
                MaterialIssue.issue_type == "issue",
            )
        )
        if original is None:
            raise InventoryNotFound(
                "Company- and Branch-scoped material issue not found"
            )
        if not key:
            raise InventoryValidation("Issue reversal idempotency key is required")
        prior = await session.scalar(
            select(MaterialIssue).where(
                MaterialIssue.company_id == spec.company_id,
                MaterialIssue.reversal_of_issue_id == original.id,
            )
        )
        if prior:
            raise InventoryConflict("Material issue was already reversed")
        reservation = await self._locked_reservation(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            reservation_id=original.reservation_id,
            item_id=original.item_id,
            location_id=original.location_id,
        )
        concurrent_replay = await session.scalar(
            select(MaterialIssue).where(
                MaterialIssue.company_id == spec.company_id,
                MaterialIssue.idempotency_key == key,
            )
        )
        if concurrent_replay:
            if concurrent_replay.reversal_of_issue_id != spec.issue_id:
                raise InventoryConflict("Issue reversal idempotency key was reused")
            return self._issue_record(concurrent_replay)
        self._assert_version(reservation.version, spec.expected_reservation_version)
        if reservation.status not in {"allocated", "fulfilled"}:
            raise InventoryConflict(
                "Material issue cannot be reversed in current state"
            )
        reversal = MaterialIssue(
            id=uuid4(),
            company_id=original.company_id,
            branch_id=original.branch_id,
            reservation_id=original.reservation_id,
            allocation_id=original.allocation_id,
            issue_type="reversal",
            item_id=original.item_id,
            location_id=original.location_id,
            quantity=original.quantity,
            stocking_unit=original.stocking_unit,
            occurred_at=spec.occurred_at,
            actor_user_id=spec.actor_user_id,
            idempotency_key=key,
            movement_id=UUID(int=0),
            reversal_of_issue_id=original.id,
            external_reference_type=original.external_reference_type,
            external_reference_id=original.external_reference_id,
        )
        movement = await self.post_movement(
            session,
            spec=PostStockMovement(
                company_id=original.company_id,
                branch_id=original.branch_id,
                item_id=original.item_id,
                movement_type="material_issue_reversal",
                quantity=original.quantity,
                occurred_at=spec.occurred_at,
                actor_user_id=spec.actor_user_id,
                idempotency_key=f"material-issue-reversal:{key}",
                destination_location_id=original.location_id,
                provenance_type="material_issue_reversal",
                provenance_id=reversal.id,
                reversal_of_id=original.movement_id,
            ),
        )
        reversal.movement_id = movement.id
        session.add(reversal)
        quantity = await self._locked_quantity(
            session,
            company_id=original.company_id,
            branch_id=original.branch_id,
            item_id=original.item_id,
            location_id=original.location_id,
        )
        quantity.reserved += original.quantity
        quantity.version += 1
        quantity.updated_at = datetime.now(timezone.utc)
        old_status = reservation.status
        old_version = reservation.version
        reservation.issued_quantity -= original.quantity
        reservation.status = "allocated"
        reservation.version += 1
        reservation.updated_by_user_id = spec.actor_user_id
        reservation.updated_at = datetime.now(timezone.utc)
        if old_status != reservation.status:
            self._add_lifecycle_event(
                session,
                reservation=reservation,
                from_status=old_status,
                from_version=old_version,
                to_status=reservation.status,
                actor_user_id=spec.actor_user_id,
                idempotency_key=f"reversal:{key}",
            )
        await session.flush()
        return self._issue_record(reversal)

    async def release_reservation(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        reservation_id: UUID,
        actor_user_id: UUID,
    ) -> ReservationRecord:
        reservation = await session.scalar(
            select(InventoryReservation)
            .where(
                InventoryReservation.company_id == company_id,
                InventoryReservation.id == reservation_id,
            )
            .with_for_update()
        )
        if reservation is None:
            raise InventoryNotFound("Reservation not found")
        if reservation.status == "released":
            return self._reservation_record(reservation)
        if reservation.status not in {"requested", "partially_allocated", "allocated"}:
            raise InventoryConflict("Reservation cannot be released from current state")
        outstanding = reservation.allocated_quantity - reservation.issued_quantity
        if outstanding:
            quantity = await self._locked_quantity(
                session,
                company_id=reservation.company_id,
                branch_id=reservation.branch_id,
                item_id=reservation.item_id,
                location_id=reservation.location_id,
            )
            quantity.reserved -= outstanding
            quantity.version += 1
            quantity.updated_at = datetime.now(timezone.utc)
        old_status = reservation.status
        old_version = reservation.version
        reservation.status = "released"
        reservation.version += 1
        reservation.updated_by_user_id = actor_user_id
        reservation.updated_at = datetime.now(timezone.utc)
        self._add_lifecycle_event(
            session,
            reservation=reservation,
            from_status=old_status,
            from_version=old_version,
            to_status="released",
            actor_user_id=actor_user_id,
            idempotency_key=f"legacy-release:{reservation.id}",
        )
        await session.flush()
        return self._reservation_record(reservation)

    async def _locked_reservation(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        reservation_id: UUID,
        item_id: UUID | None = None,
        location_id: UUID | None = None,
    ) -> InventoryReservation:
        conditions = [
            InventoryReservation.company_id == company_id,
            InventoryReservation.branch_id == branch_id,
            InventoryReservation.id == reservation_id,
        ]
        if item_id is not None:
            conditions.append(InventoryReservation.item_id == item_id)
        if location_id is not None:
            conditions.append(InventoryReservation.location_id == location_id)
        reservation = await session.scalar(
            select(InventoryReservation).where(*conditions).with_for_update()
        )
        if reservation is None:
            raise InventoryNotFound(
                "Company-, Branch-, item-, and location-scoped reservation not found"
            )
        return reservation

    async def _scoped_allocation(
        self, session: AsyncSession, spec: PostMaterialIssue
    ) -> ReservationAllocation:
        allocation = await session.scalar(
            select(ReservationAllocation).where(
                ReservationAllocation.company_id == spec.company_id,
                ReservationAllocation.branch_id == spec.branch_id,
                ReservationAllocation.reservation_id == spec.reservation_id,
                ReservationAllocation.item_id == spec.item_id,
                ReservationAllocation.location_id == spec.location_id,
                ReservationAllocation.id == spec.allocation_id,
            )
        )
        if allocation is None:
            raise InventoryNotFound("Scoped reservation allocation not found")
        return allocation

    async def _active_item(
        self, session: AsyncSession, *, company_id: UUID, item_id: UUID
    ) -> InventoryItem:
        item = await session.scalar(
            select(InventoryItem).where(
                InventoryItem.company_id == company_id,
                InventoryItem.id == item_id,
                InventoryItem.status == "active",
            )
        )
        if item is None:
            raise InventoryNotFound("Active Inventory item not found")
        return item

    async def _active_location(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        location_id: UUID,
    ) -> StockLocation:
        location = await session.scalar(
            select(StockLocation).where(
                StockLocation.company_id == company_id,
                StockLocation.branch_id == branch_id,
                StockLocation.id == location_id,
                StockLocation.status == "active",
            )
        )
        if location is None:
            raise InventoryNotFound(
                "Active Company- and Branch-scoped location not found"
            )
        return location

    async def _locked_quantity(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        item_id: UUID,
        location_id: UUID,
    ) -> InventoryQuantity:
        quantity = await session.scalar(
            select(InventoryQuantity)
            .where(
                InventoryQuantity.company_id == company_id,
                InventoryQuantity.branch_id == branch_id,
                InventoryQuantity.item_id == item_id,
                InventoryQuantity.location_id == location_id,
            )
            .with_for_update()
        )
        if quantity is None:
            quantity = InventoryQuantity(
                company_id=company_id,
                branch_id=branch_id,
                item_id=item_id,
                location_id=location_id,
                on_hand=Decimal(0),
                reserved=Decimal(0),
                version=1,
            )
            session.add(quantity)
            await session.flush()
        return quantity

    async def _locked_cycle(
        self, session: AsyncSession, company_id: UUID, session_id: UUID
    ) -> CycleCountSession:
        cycle = await session.scalar(
            select(CycleCountSession)
            .where(
                CycleCountSession.company_id == company_id,
                CycleCountSession.id == session_id,
            )
            .with_for_update()
        )
        if cycle is None:
            raise InventoryNotFound("Company-scoped cycle count not found")
        return cycle

    async def _authoritative_on_hand(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        item_id: UUID,
        location_id: UUID,
    ) -> Decimal:
        signed_quantity = case(
            (
                StockMovement.destination_location_id == location_id,
                StockMovement.quantity,
            ),
            (StockMovement.source_location_id == location_id, -StockMovement.quantity),
            else_=Decimal(0),
        )
        value = await session.scalar(
            select(func.coalesce(func.sum(signed_quantity), 0)).where(
                StockMovement.company_id == company_id,
                StockMovement.branch_id == branch_id,
                StockMovement.item_id == item_id,
                (StockMovement.source_location_id == location_id)
                | (StockMovement.destination_location_id == location_id),
            )
        )
        return Decimal(value or 0)

    async def _reconcile_quantity(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        item_id: UUID,
        location_id: UUID,
    ) -> InventoryQuantity:
        quantity = await self._locked_quantity(
            session,
            company_id=company_id,
            branch_id=branch_id,
            item_id=item_id,
            location_id=location_id,
        )
        authoritative = await self._authoritative_on_hand(
            session,
            company_id=company_id,
            branch_id=branch_id,
            item_id=item_id,
            location_id=location_id,
        )
        if authoritative < quantity.reserved:
            raise InventoryConflict(
                "Authoritative movement evidence is below reserved quantity"
            )
        if quantity.on_hand != authoritative:
            quantity.on_hand = authoritative
            quantity.version += 1
            quantity.updated_at = datetime.now(timezone.utc)
            await session.flush()
        return quantity

    @staticmethod
    def _validate_quantity(item: InventoryItem, quantity: Decimal) -> None:
        if quantity <= 0:
            raise InventoryValidation("Quantity must be positive")
        if not item.allow_fractional and quantity != quantity.to_integral_value():
            raise InventoryValidation("Item does not allow fractional quantity")

    @staticmethod
    def _validate_movement_shape(spec: PostStockMovement) -> None:
        if not spec.idempotency_key.strip():
            raise InventoryValidation("Movement idempotency key is required")
        inbound = {
            "opening",
            "increase",
            "adjustment_in",
            "material_issue_reversal",
            "purchase_receipt",
        }
        outbound = {"decrease", "adjustment_out", "material_issue", "purchase_return"}
        if spec.movement_type in inbound:
            valid = (
                spec.source_location_id is None
                and spec.destination_location_id is not None
            )
        elif spec.movement_type in outbound:
            valid = (
                spec.source_location_id is not None
                and spec.destination_location_id is None
            )
        elif spec.movement_type == "transfer":
            valid = (
                spec.source_location_id is not None
                and spec.destination_location_id is not None
                and spec.source_location_id != spec.destination_location_id
            )
        else:
            valid = False
        if not valid:
            raise InventoryValidation("Movement type and locations are inconsistent")
        if (spec.provenance_type is None) != (spec.provenance_id is None):
            raise InventoryValidation("Movement provenance must be complete")
        valuation = (spec.unit_cost, spec.currency, spec.valuation_method)
        if any(value is not None for value in valuation) and any(
            value is None for value in valuation
        ):
            raise InventoryValidation("Valuation evidence must be complete")

    @staticmethod
    def _assert_same_movement(movement: StockMovement, spec: PostStockMovement) -> None:
        values = (
            movement.branch_id == spec.branch_id,
            movement.item_id == spec.item_id,
            movement.movement_type == spec.movement_type,
            movement.source_location_id == spec.source_location_id,
            movement.destination_location_id == spec.destination_location_id,
            movement.quantity == spec.quantity,
        )
        if not all(values):
            raise InventoryConflict("Movement idempotency key was reused")

    @staticmethod
    def _assert_same_reservation(
        reservation: InventoryReservation, spec: CreateReservation
    ) -> None:
        values = (
            reservation.branch_id == spec.branch_id,
            reservation.item_id == spec.item_id,
            reservation.location_id == spec.location_id,
            reservation.quantity == spec.quantity,
            reservation.demand_type == spec.demand_type.strip(),
            reservation.demand_id == spec.demand_id,
        )
        if not all(values):
            raise InventoryConflict("Reservation idempotency key was reused")

    @staticmethod
    async def _lock_idempotency(
        session: AsyncSession, company_id: UUID, operation: str, key: str
    ) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"inventory:{operation}:{company_id}:{key}"},
        )

    @staticmethod
    def _authorize_branch(
        branch_id: UUID, authorized_branch_ids: tuple[UUID, ...]
    ) -> None:
        if branch_id not in authorized_branch_ids:
            raise InventoryNotFound("Authorized Branch-scoped Inventory access denied")

    @staticmethod
    def _assert_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise InventoryConflict(
                f"Stale reservation version: expected {expected}, found {actual}"
            )

    @staticmethod
    def _validate_external_reference(
        reference_type: str | None, reference_id: UUID | None
    ) -> None:
        if (reference_type is None) != (reference_id is None):
            raise InventoryValidation("External material reference must be complete")
        if reference_type is not None and not reference_type.strip():
            raise InventoryValidation("External material reference type is required")

    @staticmethod
    def _add_lifecycle_event(
        session: AsyncSession,
        *,
        reservation: InventoryReservation,
        from_status: str,
        from_version: int,
        to_status: str,
        actor_user_id: UUID,
        idempotency_key: str,
    ) -> None:
        session.add(
            ReservationLifecycleEvent(
                company_id=reservation.company_id,
                reservation_id=reservation.id,
                from_status=from_status,
                to_status=to_status,
                from_version=from_version,
                idempotency_key=idempotency_key,
                actor_user_id=actor_user_id,
            )
        )

    @staticmethod
    def _assert_same_allocation(
        allocation: ReservationAllocation, spec: AllocateReservation
    ) -> None:
        requested = (
            allocation.requested_quantity if spec.quantity is None else spec.quantity
        )
        values = (
            allocation.branch_id == spec.branch_id,
            allocation.reservation_id == spec.reservation_id,
            allocation.item_id == spec.item_id,
            allocation.location_id == spec.location_id,
            allocation.allocated_by_user_id == spec.actor_user_id,
            allocation.reservation_version == spec.expected_version,
            allocation.requested_quantity == requested,
            allocation.partial_allowed == spec.allow_partial,
        )
        if not all(values):
            raise InventoryConflict("Allocation idempotency key was reused")

    @staticmethod
    def _assert_same_issue(issue: MaterialIssue, spec: PostMaterialIssue) -> None:
        values = (
            issue.issue_type == "issue",
            issue.branch_id == spec.branch_id,
            issue.reservation_id == spec.reservation_id,
            issue.allocation_id == spec.allocation_id,
            issue.item_id == spec.item_id,
            issue.location_id == spec.location_id,
            issue.occurred_at == spec.occurred_at,
            issue.actor_user_id == spec.actor_user_id,
            issue.external_reference_type == spec.external_reference_type,
            issue.external_reference_id == spec.external_reference_id,
        )
        if not all(values):
            raise InventoryConflict("Material issue idempotency key was reused")

    @staticmethod
    def _assert_same_adjustment(
        adjustment: InventoryAdjustment, spec: PostInventoryAdjustment
    ) -> None:
        values = (
            adjustment.branch_id == spec.branch_id,
            adjustment.item_id == spec.item_id,
            adjustment.location_id == spec.location_id,
            adjustment.reason == spec.reason.strip().lower(),
            adjustment.quantity_delta == spec.quantity_delta,
            adjustment.note == spec.note.strip(),
            adjustment.occurred_at == spec.occurred_at,
            adjustment.actor_user_id == spec.actor_user_id,
            adjustment.cycle_count_entry_id == spec.cycle_count_entry_id,
        )
        if not all(values):
            raise InventoryConflict("Adjustment idempotency key was reused")

    @staticmethod
    def _item_record(item: InventoryItem) -> InventoryItemRecord:
        return InventoryItemRecord(
            id=item.id,
            company_id=item.company_id,
            code=item.code,
            name=item.name,
            stocking_unit=item.stocking_unit,
            allow_fractional=item.allow_fractional,
            status=item.status,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _location_record(location: StockLocation) -> StockLocationRecord:
        return StockLocationRecord(
            id=location.id,
            company_id=location.company_id,
            branch_id=location.branch_id,
            code=location.code,
            name=location.name,
            location_type=location.location_type,
            status=location.status,
            external_entity_type=location.external_entity_type,
            external_entity_id=location.external_entity_id,
            version=location.version,
            created_at=location.created_at,
            updated_at=location.updated_at,
        )

    @staticmethod
    def _quantity_record(quantity: InventoryQuantity) -> QuantityRecord:
        return QuantityRecord(
            item_id=quantity.item_id,
            location_id=quantity.location_id,
            company_id=quantity.company_id,
            branch_id=quantity.branch_id,
            on_hand=quantity.on_hand,
            reserved=quantity.reserved,
            available=quantity.on_hand - quantity.reserved,
            version=quantity.version,
            updated_at=quantity.updated_at,
        )

    @staticmethod
    def _movement_record(movement: StockMovement) -> StockMovementRecord:
        return StockMovementRecord(
            id=movement.id,
            company_id=movement.company_id,
            branch_id=movement.branch_id,
            item_id=movement.item_id,
            movement_type=movement.movement_type,
            source_location_id=movement.source_location_id,
            destination_location_id=movement.destination_location_id,
            quantity=movement.quantity,
            stocking_unit=movement.stocking_unit,
            occurred_at=movement.occurred_at,
            posted_at=movement.posted_at,
            provenance_type=movement.provenance_type,
            provenance_id=movement.provenance_id,
            idempotency_key=movement.idempotency_key,
            reversal_of_id=movement.reversal_of_id,
            unit_cost=movement.unit_cost,
            currency=movement.currency,
            valuation_method=movement.valuation_method,
        )

    @staticmethod
    def _reservation_record(reservation: InventoryReservation) -> ReservationRecord:
        return ReservationRecord(
            id=reservation.id,
            company_id=reservation.company_id,
            branch_id=reservation.branch_id,
            item_id=reservation.item_id,
            location_id=reservation.location_id,
            quantity=reservation.quantity,
            allocated_quantity=reservation.allocated_quantity,
            issued_quantity=reservation.issued_quantity,
            stocking_unit=reservation.stocking_unit,
            demand_type=reservation.demand_type,
            demand_id=reservation.demand_id,
            status=reservation.status,
            expires_at=reservation.expires_at,
            idempotency_key=reservation.idempotency_key,
            version=reservation.version,
            created_at=reservation.created_at,
            updated_at=reservation.updated_at,
        )

    @staticmethod
    def _allocation_record(allocation: ReservationAllocation) -> AllocationRecord:
        return AllocationRecord(
            id=allocation.id,
            company_id=allocation.company_id,
            branch_id=allocation.branch_id,
            reservation_id=allocation.reservation_id,
            item_id=allocation.item_id,
            location_id=allocation.location_id,
            quantity=allocation.quantity,
            requested_quantity=allocation.requested_quantity,
            partial_allowed=allocation.partial_allowed,
            stocking_unit=allocation.stocking_unit,
            reservation_version=allocation.reservation_version,
            idempotency_key=allocation.idempotency_key,
            allocated_by_user_id=allocation.allocated_by_user_id,
            allocated_at=allocation.allocated_at,
        )

    @staticmethod
    def _issue_record(issue: MaterialIssue) -> MaterialIssueRecord:
        return MaterialIssueRecord(
            id=issue.id,
            company_id=issue.company_id,
            branch_id=issue.branch_id,
            reservation_id=issue.reservation_id,
            allocation_id=issue.allocation_id,
            issue_type=issue.issue_type,
            item_id=issue.item_id,
            location_id=issue.location_id,
            quantity=issue.quantity,
            stocking_unit=issue.stocking_unit,
            occurred_at=issue.occurred_at,
            posted_at=issue.posted_at,
            actor_user_id=issue.actor_user_id,
            idempotency_key=issue.idempotency_key,
            movement_id=issue.movement_id,
            reversal_of_issue_id=issue.reversal_of_issue_id,
            external_reference_type=issue.external_reference_type,
            external_reference_id=issue.external_reference_id,
        )

    @staticmethod
    def _adjustment_record(adjustment: InventoryAdjustment) -> AdjustmentRecord:
        return AdjustmentRecord(
            id=adjustment.id,
            company_id=adjustment.company_id,
            branch_id=adjustment.branch_id,
            item_id=adjustment.item_id,
            location_id=adjustment.location_id,
            reason=adjustment.reason,
            quantity_delta=adjustment.quantity_delta,
            stocking_unit=adjustment.stocking_unit,
            note=adjustment.note,
            occurred_at=adjustment.occurred_at,
            posted_at=adjustment.posted_at,
            actor_user_id=adjustment.actor_user_id,
            idempotency_key=adjustment.idempotency_key,
            movement_id=adjustment.movement_id,
            cycle_count_entry_id=adjustment.cycle_count_entry_id,
        )

    @staticmethod
    def _cycle_entry_record(entry: CycleCountEntry) -> CycleCountEntryRecord:
        return CycleCountEntryRecord(
            id=entry.id,
            company_id=entry.company_id,
            session_id=entry.session_id,
            item_id=entry.item_id,
            expected_quantity=entry.expected_quantity,
            counted_quantity=entry.counted_quantity,
            variance=entry.counted_quantity - entry.expected_quantity,
            stocking_unit=entry.stocking_unit,
            counted_at=entry.counted_at,
            counted_by_user_id=entry.counted_by_user_id,
            idempotency_key=entry.idempotency_key,
        )

    @staticmethod
    def _cycle_session_record(cycle: CycleCountSession) -> CycleCountSessionRecord:
        return CycleCountSessionRecord(
            id=cycle.id,
            company_id=cycle.company_id,
            branch_id=cycle.branch_id,
            location_id=cycle.location_id,
            name=cycle.name,
            status=cycle.status,
            idempotency_key=cycle.idempotency_key,
            version=cycle.version,
            started_by_user_id=cycle.started_by_user_id,
            completed_by_user_id=cycle.completed_by_user_id,
            started_at=cycle.started_at,
            completed_at=cycle.completed_at,
        )
