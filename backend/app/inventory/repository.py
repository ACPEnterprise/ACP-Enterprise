from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.contracts import (
    CreateInventoryItem,
    CreateReservation,
    CreateStockLocation,
    InventoryItemRecord,
    PostStockMovement,
    QuantityRecord,
    ReservationRecord,
    StockLocationRecord,
    StockMovementRecord,
)
from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.models import (
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
            if source.on_hand - spec.quantity < source.reserved:
                raise InventoryConflict(
                    "Movement would make available quantity negative"
                )
            source.on_hand -= spec.quantity
            source.version += 1
            source.updated_at = datetime.now(timezone.utc)
        if spec.destination_location_id:
            destination = await self._locked_quantity(
                session,
                company_id=spec.company_id,
                branch_id=spec.branch_id,
                item_id=spec.item_id,
                location_id=spec.destination_location_id,
            )
            destination.on_hand += spec.quantity
            destination.version += 1
            destination.updated_at = datetime.now(timezone.utc)
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
        return self._movement_record(movement)

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
