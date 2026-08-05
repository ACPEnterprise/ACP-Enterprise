from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.inventory.contracts import RecordCycleCount, StartCycleCount
from app.inventory.errors import InventoryConflict, InventoryNotFound
from app.inventory.models import InventoryAdjustment, StockMovement
from tests.inventory.test_inventory_foundation import (
    inventory_fixture,  # noqa: F401
    opening_spec,
    seed_foundation,
)


@pytest.mark.asyncio
async def test_complete_cycle_count_posts_deterministic_variance_once(
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
        cycle = await repository.start_cycle_count(
            session,
            spec=StartCycleCount(
                company_id=company.id,
                branch_id=branch.id,
                location_id=warehouse.id,
                name="August warehouse count",
                actor_user_id=actor.id,
                idempotency_key=f"cycle-{uuid4()}",
            ),
        )
        entry_spec = RecordCycleCount(
            company_id=company.id,
            session_id=cycle.id,
            item_id=item.id,
            counted_quantity=Decimal(18),
            counted_at=datetime.now(timezone.utc),
            actor_user_id=actor.id,
            idempotency_key=f"count-{uuid4()}",
        )
        entry = await repository.record_cycle_count(session, spec=entry_spec)
        duplicate_entry = await repository.record_cycle_count(session, spec=entry_spec)
        assert entry == duplicate_entry
        assert entry.expected_quantity == Decimal("20.5")
        assert entry.variance == Decimal("-2.5")
        completed = await repository.complete_cycle_count(
            session,
            company_id=company.id,
            session_id=cycle.id,
            actor_user_id=actor.id,
        )
        duplicate_completion = await repository.complete_cycle_count(
            session,
            company_id=company.id,
            session_id=cycle.id,
            actor_user_id=actor.id,
        )
        assert completed == duplicate_completion
        assert completed.status == "completed"
        quantity = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert quantity.on_hand == Decimal(18)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(InventoryAdjustment)
                .where(InventoryAdjustment.company_id == company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.company_id == company.id)
            )
            == 2
        )
        with pytest.raises(InventoryConflict, match="cannot accept entries"):
            await repository.record_cycle_count(
                session,
                spec=RecordCycleCount(
                    company_id=company.id,
                    session_id=cycle.id,
                    item_id=item.id,
                    counted_quantity=Decimal(17),
                    counted_at=datetime.now(timezone.utc),
                    actor_user_id=actor.id,
                    idempotency_key=f"late-{uuid4()}",
                ),
            )


@pytest.mark.asyncio
async def test_cycle_count_scope_and_empty_completion_fail_closed(
    inventory_fixture,  # noqa: F811
) -> None:
    factory, company, branch, other_branch, actor = inventory_fixture
    repository, _, warehouse, _ = await seed_foundation(factory, company, branch, actor)
    async with factory() as session, session.begin():
        with pytest.raises(InventoryNotFound, match="Company- and Branch-scoped"):
            await repository.start_cycle_count(
                session,
                spec=StartCycleCount(
                    company_id=company.id,
                    branch_id=other_branch.id,
                    location_id=warehouse.id,
                    name="Wrong branch",
                    actor_user_id=actor.id,
                    idempotency_key=f"cycle-{uuid4()}",
                ),
            )
        cycle = await repository.start_cycle_count(
            session,
            spec=StartCycleCount(
                company_id=company.id,
                branch_id=branch.id,
                location_id=warehouse.id,
                name="Empty",
                actor_user_id=actor.id,
                idempotency_key=f"cycle-{uuid4()}",
            ),
        )
        with pytest.raises(InventoryConflict, match="at least one entry"):
            await repository.complete_cycle_count(
                session,
                company_id=company.id,
                session_id=cycle.id,
                actor_user_id=actor.id,
            )
