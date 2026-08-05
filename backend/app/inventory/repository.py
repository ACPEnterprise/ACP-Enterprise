from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.contracts import (
    AdjustmentRecord,
    CreateInventoryItem,
    CreateReservation,
    CreateStockLocation,
    CycleCountEntryRecord,
    CycleCountSessionRecord,
    InventoryItemRecord,
    PostInventoryAdjustment,
    PostStockMovement,
    QuantityRecord,
    RecordCycleCount,
    ReservationRecord,
    StartCycleCount,
    StockLocationRecord,
    StockMovementRecord,
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

    async def post_movement(
        self, session: AsyncSession, *, spec: PostStockMovement
    ) -> StockMovementRecord:
        existing = await session.scalar(
            select(StockMovement).where(
                StockMovement.company_id == spec.company_id,
                StockMovement.idempotency_key == spec.idempotency_key,
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
            idempotency_key=spec.idempotency_key.strip(),
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
        existing = await session.scalar(
            select(InventoryAdjustment).where(
                InventoryAdjustment.company_id == spec.company_id,
                InventoryAdjustment.idempotency_key == spec.idempotency_key.strip(),
            )
        )
        if existing:
            self._assert_same_adjustment(existing, spec)
            return self._adjustment_record(existing)
        reason = spec.reason.strip().lower()
        note = spec.note.strip()
        key = spec.idempotency_key.strip()
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
        if not key or not spec.name.strip():
            raise InventoryValidation(
                "Cycle count name and idempotency key are required"
            )
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

    async def record_cycle_count(
        self, session: AsyncSession, *, spec: RecordCycleCount
    ) -> CycleCountEntryRecord:
        key = spec.idempotency_key.strip()
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
        if not key:
            raise InventoryValidation("Cycle count entry idempotency key is required")
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
    ) -> CycleCountSessionRecord:
        cycle = await self._locked_cycle(session, company_id, session_id)
        if cycle.status == "completed":
            return self._cycle_session_record(cycle)
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
        existing = await session.scalar(
            select(InventoryReservation).where(
                InventoryReservation.company_id == spec.company_id,
                InventoryReservation.idempotency_key == spec.idempotency_key,
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
        quantity = await self._locked_quantity(
            session,
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
        )
        if quantity.on_hand - quantity.reserved < spec.quantity:
            raise InventoryConflict("Insufficient available quantity")
        quantity.reserved += spec.quantity
        quantity.version += 1
        quantity.updated_at = datetime.now(timezone.utc)
        reservation = InventoryReservation(
            company_id=spec.company_id,
            branch_id=spec.branch_id,
            item_id=spec.item_id,
            location_id=spec.location_id,
            quantity=spec.quantity,
            stocking_unit=item.stocking_unit,
            demand_type=spec.demand_type.strip(),
            demand_id=spec.demand_id,
            status="active",
            expires_at=spec.expires_at,
            idempotency_key=spec.idempotency_key.strip(),
            version=1,
            created_by_user_id=spec.actor_user_id,
            updated_by_user_id=spec.actor_user_id,
        )
        session.add(reservation)
        await session.flush()
        return self._reservation_record(reservation)

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
        if reservation.status != "active":
            raise InventoryConflict("Only active reservations can be released")
        quantity = await self._locked_quantity(
            session,
            company_id=reservation.company_id,
            branch_id=reservation.branch_id,
            item_id=reservation.item_id,
            location_id=reservation.location_id,
        )
        quantity.reserved -= reservation.quantity
        quantity.version += 1
        quantity.updated_at = datetime.now(timezone.utc)
        reservation.status = "released"
        reservation.version += 1
        reservation.updated_by_user_id = actor_user_id
        reservation.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return self._reservation_record(reservation)

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
        inbound = {"opening", "increase", "adjustment_in"}
        outbound = {"decrease", "adjustment_out"}
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
