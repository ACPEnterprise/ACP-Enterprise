from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.events.models import BusinessEvent
from app.inventory.contracts import CreateStockLocation
from app.inventory.errors import InventoryNotFound
from app.inventory.schemas import (
    AdjustmentCreate,
    CycleCountComplete,
    CycleCountRecord,
    CycleCountStart,
    LocationCreate,
    ReservationAllocate,
    ReservationCreate,
    TransferCreate,
)
from app.inventory.service import InventoryService
from app.platform.company.membership_models import Membership
from app.platform.permissions.authorization import AuthorizationContext
from sqlalchemy import func, select

from tests.inventory.test_inventory_foundation import (
    inventory_fixture,  # noqa: F401
    opening_spec,
    seed_foundation,
)


async def context(factory, company, branch, actor) -> AuthorizationContext:
    async with factory() as session, session.begin():
        membership = Membership(
            user_id=actor.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
        )
        session.add(membership)
        await session.flush()
    return AuthorizationContext(
        user=actor,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=1,
    )


@pytest.mark.asyncio
async def test_overview_and_transfer_are_scoped_atomic_and_evented(
    inventory_fixture,  # noqa: F811
) -> None:
    factory, company, branch, other_branch, actor = inventory_fixture
    repository, item, warehouse, truck = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
    authorization = await context(factory, company, branch, actor)
    service = InventoryService(repository)
    async with factory() as session:
        overview = await service.overview(
            session, context=authorization, branch_id=branch.id
        )
        assert [record.id for record in overview.items] == [item.id]
        assert {record.id for record in overview.locations} == {
            warehouse.id,
            truck.id,
        }
        with pytest.raises(InventoryNotFound):
            await service.overview(
                session, context=authorization, branch_id=other_branch.id
            )
    key = f"transfer-{uuid4()}"
    async with factory() as session:
        movement = await service.transfer(
            session,
            context=authorization,
            data=TransferCreate(
                branch_id=branch.id,
                item_id=item.id,
                source_location_id=warehouse.id,
                destination_location_id=truck.id,
                quantity=Decimal("3.5"),
                occurred_at=datetime.now(timezone.utc),
                idempotency_key=key,
            ),
        )
    async with factory() as session:
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
        event = await session.scalar(
            select(BusinessEvent).where(BusinessEvent.entity_id == movement.id)
        )
        assert source.on_hand == Decimal(17)
        assert destination.on_hand == Decimal("3.5")
        assert event is not None
        assert event.event_type == "inventory.transfer_posted"


@pytest.mark.asyncio
async def test_repository_lists_do_not_leak_other_branches(
    inventory_fixture,  # noqa: F811
) -> None:
    factory, company, branch, other_branch, actor = inventory_fixture
    repository, _, warehouse, _ = await seed_foundation(factory, company, branch, actor)
    async with factory() as session, session.begin():
        await repository.create_location(
            session,
            spec=CreateStockLocation(
                company_id=company.id,
                branch_id=other_branch.id,
                code="other-only",
                name="Other Branch",
                location_type="warehouse",
                actor_user_id=actor.id,
            ),
        )
    async with factory() as session:
        records = await repository.list_locations(
            session, company_id=company.id, branch_ids=(branch.id,)
        )
        assert warehouse.id in {record.id for record in records}
        assert all(record.branch_id == branch.id for record in records)


@pytest.mark.asyncio
async def test_adjustment_and_cycle_count_operator_services_are_idempotent_and_evented(
    inventory_fixture,  # noqa: F811
) -> None:
    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
    authorization = await context(factory, company, branch, actor)
    service = InventoryService(repository)
    adjustment = AdjustmentCreate(
        branch_id=branch.id,
        item_id=item.id,
        location_id=warehouse.id,
        reason="damaged",
        quantity_delta=Decimal(-1),
        note="Synthetic damaged-count evidence",
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"adjust-{uuid4()}",
    )
    async with factory() as session:
        first = await service.post_adjustment(
            session, context=authorization, data=adjustment
        )
        replay = await service.post_adjustment(
            session, context=authorization, data=adjustment
        )
        assert first == replay
        cycle = await service.start_cycle_count(
            session,
            context=authorization,
            data=CycleCountStart(
                branch_id=branch.id,
                location_id=warehouse.id,
                name="Operator cycle count",
                idempotency_key=f"cycle-{uuid4()}",
            ),
        )
        entry_data = CycleCountRecord(
            item_id=item.id,
            counted_quantity=Decimal(18),
            counted_at=datetime.now(timezone.utc),
            idempotency_key=f"entry-{uuid4()}",
        )
        entry = await service.record_cycle_count(
            session,
            context=authorization,
            session_id=cycle.id,
            data=entry_data,
        )
        entry_replay = await service.record_cycle_count(
            session,
            context=authorization,
            session_id=cycle.id,
            data=entry_data,
        )
        assert entry == entry_replay
        completed = await service.complete_cycle_count(
            session,
            context=authorization,
            session_id=cycle.id,
            data=CycleCountComplete(expected_version=cycle.version),
        )
        assert completed.status == "completed"
        history = await service.list_cycle_counts(
            session, context=authorization, branch_id=branch.id
        )
        assert history[0].id == cycle.id
        assert history[0].entries[0].variance == Decimal("-1.5")
    async with factory() as session:
        event_counts = {
            event_type: await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == company.id,
                    BusinessEvent.event_type == event_type,
                )
            )
            for event_type in (
                "inventory.adjustment_posted",
                "inventory.cycle_count_started",
                "inventory.cycle_count_recorded",
                "inventory.cycle_count_completed",
            )
        }
        assert event_counts == {event_type: 1 for event_type in event_counts}


@pytest.mark.asyncio
async def test_operational_location_and_reservation_commands_preserve_scope_and_evidence(
    inventory_fixture,  # noqa: F811
) -> None:
    factory, company, branch, other_branch, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
    authorization = await context(factory, company, branch, actor)
    service = InventoryService(repository)

    async with factory() as session:
        location = await service.create_location(
            session,
            context=authorization,
            data=LocationCreate(
                branch_id=branch.id,
                code="service-van-7",
                name="Service Van 7",
                location_type="vehicle",
            ),
        )
        with pytest.raises(InventoryNotFound):
            await service.create_location(
                session,
                context=authorization,
                data=LocationCreate(
                    branch_id=other_branch.id,
                    code="other-branch",
                    name="Other Branch",
                    location_type="warehouse",
                ),
            )

    async with factory() as session:
        reservation = await service.create_reservation(
            session,
            context=authorization,
            data=ReservationCreate(
                branch_id=branch.id,
                item_id=item.id,
                location_id=warehouse.id,
                quantity=Decimal("2.5"),
                demand_type="job",
                demand_id=uuid4(),
                idempotency_key=f"reservation-{uuid4()}",
            ),
        )
        allocation = await service.allocate(
            session,
            context=authorization,
            reservation_id=reservation.id,
            data=ReservationAllocate(
                quantity=None,
                allow_partial=True,
                expected_version=reservation.version,
                idempotency_key=f"allocation-{uuid4()}",
            ),
        )

    async with factory() as session:
        event_types = set(
            (
                await session.scalars(
                    select(BusinessEvent.event_type).where(
                        BusinessEvent.entity_id.in_([location.id, reservation.id])
                    )
                )
            ).all()
        )
        quantity = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert event_types == {
            "inventory.location_created",
            "inventory.reservation_created",
        }
        assert allocation.quantity == Decimal("2.5")
        assert quantity.on_hand == Decimal("20.5")
        assert quantity.reserved == Decimal("2.5")
