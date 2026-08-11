import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.inventory.contracts import (
    AllocateReservation,
    CreateReservation,
    PostMaterialIssue,
    ReverseMaterialIssue,
    TransitionReservation,
)
from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.models import (
    InventoryQuantity,
    MaterialIssue,
    ReservationAllocation,
    StockMovement,
)
from tests.inventory.test_inventory_foundation import (
    inventory_fixture,  # noqa: F401
    opening_spec,
    seed_foundation,
)


async def requested(
    repository, session, company, branch, actor, item, location, amount
):
    return await repository.create_reservation(
        session,
        spec=CreateReservation(
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=location.id,
            quantity=Decimal(amount),
            demand_type="external_material_request",
            demand_id=uuid4(),
            actor_user_id=actor.id,
            idempotency_key=f"reservation-{uuid4()}",
        ),
    )


def allocation_spec(company, branch, actor, item, location, reservation, **changes):
    spec = AllocateReservation(
        company_id=company.id,
        branch_id=branch.id,
        reservation_id=reservation.id,
        item_id=item.id,
        location_id=location.id,
        actor_user_id=actor.id,
        authorized_branch_ids=(branch.id,),
        expected_version=reservation.version,
        idempotency_key=f"allocation-{uuid4()}",
    )
    return replace(spec, **changes)


@pytest.mark.asyncio
async def test_full_allocation_is_scoped_idempotent_and_stale_safe(
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
        reservation = await requested(
            repository, session, company, branch, actor, item, warehouse, "6"
        )
        spec = allocation_spec(company, branch, actor, item, warehouse, reservation)
        allocation = await repository.allocate_reservation(session, spec=spec)
        replay = await repository.allocate_reservation(session, spec=spec)
        assert allocation == replay
        assert allocation.quantity == Decimal(6)
        quantity = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert quantity.reserved == Decimal(6)
        with pytest.raises(InventoryConflict, match="Stale reservation version"):
            await repository.transition_reservation(
                session,
                spec=TransitionReservation(
                    company_id=company.id,
                    branch_id=branch.id,
                    reservation_id=reservation.id,
                    actor_user_id=actor.id,
                    authorized_branch_ids=(branch.id,),
                    expected_version=reservation.version,
                    target_status="released",
                    idempotency_key=f"release-{uuid4()}",
                ),
            )


@pytest.mark.asyncio
async def test_partial_allocation_requires_explicit_contract_and_can_complete(
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
        reservation = await requested(
            repository, session, company, branch, actor, item, warehouse, "10"
        )
        base = allocation_spec(company, branch, actor, item, warehouse, reservation)
        with pytest.raises(InventoryValidation, match="explicitly allowed"):
            await repository.allocate_reservation(
                session, spec=replace(base, quantity=Decimal(4))
            )
        partial = await repository.allocate_reservation(
            session,
            spec=replace(
                base,
                quantity=Decimal(4),
                allow_partial=True,
                idempotency_key=f"partial-{uuid4()}",
            ),
        )
        assert partial.quantity == Decimal(4)
        current = await repository.get_reservation(
            session,
            company_id=company.id,
            branch_id=branch.id,
            reservation_id=reservation.id,
        )
        assert current is not None
        assert current.status == "partially_allocated"
        completed = await repository.allocate_reservation(
            session,
            spec=allocation_spec(
                company,
                branch,
                actor,
                item,
                warehouse,
                current,
            ),
        )
        assert completed.quantity == Decimal(6)
        final = await repository.get_reservation(
            session,
            company_id=company.id,
            branch_id=branch.id,
            reservation_id=reservation.id,
        )
        assert final is not None and final.status == "allocated"
        ordered = await repository.list_allocations(
            session,
            company_id=company.id,
            branch_id=branch.id,
            reservation_id=reservation.id,
        )
        assert [row.quantity for row in ordered] == [Decimal(4), Decimal(6)]


@pytest.mark.asyncio
async def test_insufficient_stock_and_scope_mismatch_fail_closed(
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
        reservation = await requested(
            repository, session, company, branch, actor, item, warehouse, "30"
        )
        base = allocation_spec(company, branch, actor, item, warehouse, reservation)
        with pytest.raises(InventoryConflict, match="Insufficient available"):
            await repository.allocate_reservation(session, spec=base)
        with pytest.raises(InventoryNotFound, match="Authorized Branch"):
            await repository.allocate_reservation(
                session,
                spec=replace(
                    base,
                    authorized_branch_ids=(other_branch.id,),
                    idempotency_key=f"unauthorized-{uuid4()}",
                ),
            )
        with pytest.raises(InventoryNotFound, match="scoped reservation"):
            await repository.allocate_reservation(
                session,
                spec=replace(
                    base,
                    location_id=truck.id,
                    idempotency_key=f"wrong-location-{uuid4()}",
                ),
            )
        with pytest.raises(InventoryNotFound, match="scoped reservation"):
            await repository.allocate_reservation(
                session,
                spec=replace(
                    base,
                    item_id=uuid4(),
                    idempotency_key=f"wrong-item-{uuid4()}",
                ),
            )
        with pytest.raises(InventoryNotFound, match="scoped reservation"):
            await repository.allocate_reservation(
                session,
                spec=replace(
                    base,
                    company_id=uuid4(),
                    idempotency_key=f"wrong-company-{uuid4()}",
                ),
            )
        with pytest.raises(InventoryNotFound, match="scoped reservation"):
            await repository.allocate_reservation(
                session,
                spec=replace(
                    base,
                    branch_id=other_branch.id,
                    authorized_branch_ids=(other_branch.id,),
                    idempotency_key=f"wrong-branch-{uuid4()}",
                ),
            )


@pytest.mark.asyncio
async def test_release_and_cancel_are_explicit_idempotent_transitions(
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
        reservation = await requested(
            repository, session, company, branch, actor, item, warehouse, "5"
        )
        await repository.allocate_reservation(
            session,
            spec=allocation_spec(company, branch, actor, item, warehouse, reservation),
        )
        current = await repository.get_reservation(
            session,
            company_id=company.id,
            branch_id=branch.id,
            reservation_id=reservation.id,
        )
        assert current is not None
        transition = TransitionReservation(
            company_id=company.id,
            branch_id=branch.id,
            reservation_id=reservation.id,
            actor_user_id=actor.id,
            authorized_branch_ids=(branch.id,),
            expected_version=current.version,
            target_status="released",
            idempotency_key=f"release-{uuid4()}",
        )
        released = await repository.transition_reservation(session, spec=transition)
        replay = await repository.transition_reservation(session, spec=transition)
        assert released == replay and released.status == "released"
        with pytest.raises(InventoryConflict, match="not valid"):
            await repository.transition_reservation(
                session,
                spec=replace(
                    transition,
                    target_status="cancelled",
                    expected_version=released.version,
                    idempotency_key=f"cancel-{uuid4()}",
                ),
            )
        cancellable = await requested(
            repository, session, company, branch, actor, item, warehouse, "2"
        )
        cancellation = TransitionReservation(
            company_id=company.id,
            branch_id=branch.id,
            reservation_id=cancellable.id,
            actor_user_id=actor.id,
            authorized_branch_ids=(branch.id,),
            expected_version=cancellable.version,
            target_status="cancelled",
            idempotency_key=f"cancel-{uuid4()}",
        )
        cancelled = await repository.transition_reservation(session, spec=cancellation)
        assert cancelled.status == "cancelled"
        assert (
            await repository.transition_reservation(session, spec=cancellation)
            == cancelled
        )


@pytest.mark.asyncio
async def test_material_issue_and_reversal_are_linked_compensating_evidence(
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
        reservation = await requested(
            repository, session, company, branch, actor, item, warehouse, "6"
        )
        allocation = await repository.allocate_reservation(
            session,
            spec=allocation_spec(company, branch, actor, item, warehouse, reservation),
        )
        issue_spec = PostMaterialIssue(
            company_id=company.id,
            branch_id=branch.id,
            reservation_id=reservation.id,
            allocation_id=allocation.id,
            item_id=item.id,
            location_id=warehouse.id,
            occurred_at=datetime.now(timezone.utc),
            actor_user_id=actor.id,
            authorized_branch_ids=(branch.id,),
            expected_reservation_version=reservation.version + 1,
            idempotency_key=f"issue-{uuid4()}",
            external_reference_type="work_order_material_request",
            external_reference_id=uuid4(),
        )
        issue = await repository.post_material_issue(session, spec=issue_spec)
        assert await repository.post_material_issue(session, spec=issue_spec) == issue
        issue_movement = await session.get(StockMovement, issue.movement_id)
        assert issue_movement is not None
        assert issue_movement.movement_type == "material_issue"
        assert issue_movement.provenance_id == issue.id
        reversal_spec = ReverseMaterialIssue(
            company_id=company.id,
            branch_id=branch.id,
            issue_id=issue.id,
            occurred_at=datetime.now(timezone.utc),
            actor_user_id=actor.id,
            authorized_branch_ids=(branch.id,),
            expected_reservation_version=reservation.version + 2,
            idempotency_key=f"reversal-{uuid4()}",
        )
        reversal = await repository.reverse_material_issue(session, spec=reversal_spec)
        assert (
            await repository.reverse_material_issue(session, spec=reversal_spec)
            == reversal
        )
        reversal_movement = await session.get(StockMovement, reversal.movement_id)
        assert reversal_movement is not None
        assert reversal_movement.reversal_of_id == issue.movement_id
        quantity = await repository.reconcile_projection(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert quantity.on_hand == Decimal("20.5")
        assert quantity.reserved == Decimal(6)

    async with factory() as session:
        evidence = await session.scalar(
            select(MaterialIssue).where(MaterialIssue.id == issue.id)
        )
        assert evidence is not None
        with pytest.raises(DBAPIError, match="evidence is immutable"):
            await session.execute(
                update(MaterialIssue)
                .where(MaterialIssue.id == issue.id)
                .values(quantity=Decimal(1))
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_concurrent_allocations_serialize_on_quantity_projection(
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
        first = await requested(
            repository, session, company, branch, actor, item, warehouse, "15"
        )
        second = await requested(
            repository, session, company, branch, actor, item, warehouse, "15"
        )

    async def allocate(reservation):
        async with factory() as session, session.begin():
            try:
                await repository.allocate_reservation(
                    session,
                    spec=allocation_spec(
                        company, branch, actor, item, warehouse, reservation
                    ),
                )
                return "allocated"
            except InventoryConflict:
                return "insufficient"

    results = await asyncio.gather(allocate(first), allocate(second))
    assert sorted(results) == ["allocated", "insufficient"]
    async with factory() as session:
        quantity = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert quantity.reserved == Decimal(15)
        allocations = (
            await session.scalars(
                select(ReservationAllocation).where(
                    ReservationAllocation.company_id == company.id
                )
            )
        ).all()
        assert len(allocations) == 1


@pytest.mark.asyncio
async def test_projection_reconciliation_preserves_allocated_reservations(
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
        reservation = await requested(
            repository, session, company, branch, actor, item, warehouse, "4"
        )
        await repository.allocate_reservation(
            session,
            spec=allocation_spec(company, branch, actor, item, warehouse, reservation),
        )
        await session.execute(
            update(InventoryQuantity)
            .where(InventoryQuantity.company_id == company.id)
            .values(on_hand=Decimal(999))
        )
        reconciled = await repository.reconcile_projection(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert reconciled.on_hand == Decimal("20.5")
        assert reconciled.reserved == Decimal(4)
