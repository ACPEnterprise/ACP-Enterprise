from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.inventory.contracts import (
    CreateInventoryItem,
    CreateReservation,
    CreateStockLocation,
    PostStockMovement,
)
from app.inventory.errors import InventoryConflict, InventoryNotFound
from app.inventory.models import InventoryItem, StockMovement
from app.inventory.repository import InventoryRepository
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users.models import User


@pytest_asyncio.fixture
async def inventory_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Inventory Test",
            code=f"INV{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"I{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        other_branch = Branch(
            company=company,
            name="Other",
            code=f"O{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=False,
        )
        actor = User(
            normalized_email=f"inventory-{uuid4().hex}@example.test",
            first_name="Inventory",
            last_name="Owner",
            display_name="Inventory Owner",
            status="active",
        )
        session.add_all([company, branch, other_branch, actor])
        await session.flush()
    try:
        yield factory, company, branch, other_branch, actor
    finally:
        await engine.dispose()


async def seed_foundation(factory, company, branch, actor):
    repository = InventoryRepository()
    async with factory() as session, session.begin():
        item = await repository.create_item(
            session,
            spec=CreateInventoryItem(
                company_id=company.id,
                code="copper-1-2",
                name="Half-inch copper pipe",
                stocking_unit="foot",
                actor_user_id=actor.id,
            ),
        )
        warehouse = await repository.create_location(
            session,
            spec=CreateStockLocation(
                company_id=company.id,
                branch_id=branch.id,
                code="warehouse-main",
                name="Main Warehouse",
                location_type="warehouse",
                actor_user_id=actor.id,
            ),
        )
        truck = await repository.create_location(
            session,
            spec=CreateStockLocation(
                company_id=company.id,
                branch_id=branch.id,
                code="truck-12",
                name="Truck 12",
                location_type="vehicle",
                actor_user_id=actor.id,
                external_entity_type="fleet_vehicle",
                external_entity_id=uuid4(),
            ),
        )
    return repository, item, warehouse, truck


def opening_spec(company, branch, actor, item, warehouse) -> PostStockMovement:
    return PostStockMovement(
        company_id=company.id,
        branch_id=branch.id,
        item_id=item.id,
        movement_type="opening",
        destination_location_id=warehouse.id,
        quantity=Decimal("20.5"),
        occurred_at=datetime.now(timezone.utc),
        actor_user_id=actor.id,
        idempotency_key=f"opening-{uuid4()}",
        provenance_type="opening_balance",
        provenance_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_aggregates_are_scoped_and_return_immutable_dtos(
    inventory_fixture,
) -> None:
    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, truck = await seed_foundation(
        factory, company, branch, actor
    )
    assert item.company_id == company.id and item.code == "COPPER-1-2"
    assert warehouse.branch_id == branch.id and truck.location_type == "vehicle"
    assert not hasattr(item, "__table__")
    async with factory() as session:
        assert (
            await repository.get_item(session, company_id=company.id, item_id=item.id)
            == item
        )


@pytest.mark.asyncio
async def test_movement_history_drives_quantity_and_is_idempotent(
    inventory_fixture,
) -> None:
    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    spec = opening_spec(company, branch, actor, item, warehouse)
    async with factory() as session, session.begin():
        first = await repository.post_movement(session, spec=spec)
        duplicate = await repository.post_movement(session, spec=spec)
        quantity = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert first == duplicate
        assert quantity.on_hand == Decimal("20.5")
        assert quantity.available == Decimal("20.5")
        assert (
            await session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(
                    StockMovement.company_id == company.id,
                    StockMovement.item_id == item.id,
                    StockMovement.idempotency_key == spec.idempotency_key,
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_transfer_is_one_evidence_record_and_two_quantity_changes(
    inventory_fixture,
) -> None:
    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, truck = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
        transfer = await repository.post_movement(
            session,
            spec=PostStockMovement(
                company_id=company.id,
                branch_id=branch.id,
                item_id=item.id,
                movement_type="transfer",
                source_location_id=warehouse.id,
                destination_location_id=truck.id,
                quantity=Decimal("4.5"),
                occurred_at=datetime.now(timezone.utc),
                actor_user_id=actor.id,
                idempotency_key=f"transfer-{uuid4()}",
            ),
        )
        source = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        destination = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=truck.id,
        )
        assert transfer.source_location_id == warehouse.id
        assert transfer.destination_location_id == truck.id
        assert source.on_hand == Decimal(16)
        assert destination.on_hand == Decimal("4.5")


@pytest.mark.asyncio
async def test_reservation_changes_availability_and_release_is_idempotent(
    inventory_fixture,
) -> None:
    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
        reservation = await repository.create_reservation(
            session,
            spec=CreateReservation(
                company_id=company.id,
                branch_id=branch.id,
                item_id=item.id,
                location_id=warehouse.id,
                quantity=Decimal(6),
                demand_type="manual_demand",
                demand_id=uuid4(),
                actor_user_id=actor.id,
                idempotency_key=f"reservation-{uuid4()}",
            ),
        )
        reserved = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert reserved.reserved == Decimal(6)
        assert reserved.available == Decimal("14.5")
        released = await repository.release_reservation(
            session,
            company_id=company.id,
            reservation_id=reservation.id,
            actor_user_id=actor.id,
        )
        duplicate = await repository.release_reservation(
            session,
            company_id=company.id,
            reservation_id=reservation.id,
            actor_user_id=actor.id,
        )
        assert released == duplicate and released.status == "released"
        available = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert available.reserved == 0


@pytest.mark.asyncio
async def test_branch_scope_and_negative_availability_fail_closed(
    inventory_fixture,
) -> None:
    factory, company, branch, other_branch, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    spec = opening_spec(company, branch, actor, item, warehouse)
    async with factory() as session, session.begin():
        with pytest.raises(InventoryNotFound, match="Company- and Branch-scoped"):
            await repository.post_movement(
                session, spec=replace(spec, branch_id=other_branch.id)
            )
    async with factory() as session, session.begin():
        await repository.post_movement(session, spec=spec)
        with pytest.raises(InventoryConflict, match="available quantity negative"):
            await repository.post_movement(
                session,
                spec=PostStockMovement(
                    company_id=company.id,
                    branch_id=branch.id,
                    item_id=item.id,
                    movement_type="decrease",
                    source_location_id=warehouse.id,
                    quantity=Decimal(21),
                    occurred_at=datetime.now(timezone.utc),
                    actor_user_id=actor.id,
                    idempotency_key=f"decrease-{uuid4()}",
                ),
            )


@pytest.mark.asyncio
async def test_movement_history_is_database_immutable(
    inventory_fixture,
) -> None:
    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        movement = await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
    async with factory() as session:
        with pytest.raises(DBAPIError, match="movement evidence is immutable"):
            await session.execute(
                update(StockMovement)
                .where(StockMovement.id == movement.id)
                .values(quantity=Decimal(99))
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_stocking_unit_is_database_immutable_after_movement(
    inventory_fixture,
) -> None:
    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
    async with factory() as session:
        with pytest.raises(DBAPIError, match="stocking unit is immutable"):
            await session.execute(
                update(InventoryItem)
                .where(InventoryItem.id == item.id)
                .values(stocking_unit="each")
            )
        await session.rollback()
