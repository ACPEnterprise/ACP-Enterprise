from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from app.inventory.contracts import PostInventoryAdjustment
from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.models import InventoryAdjustment, InventoryQuantity, StockMovement
from tests.inventory.test_inventory_foundation import (
    inventory_fixture,  # noqa: F401
    opening_spec,
    seed_foundation,
)


def adjustment_spec(company, branch, actor, item, warehouse, reason, delta):
    return PostInventoryAdjustment(
        company_id=company.id,
        branch_id=branch.id,
        item_id=item.id,
        location_id=warehouse.id,
        reason=reason,
        quantity_delta=Decimal(delta),
        note=f"Controlled {reason} evidence",
        occurred_at=datetime.now(timezone.utc),
        actor_user_id=actor.id,
        idempotency_key=f"adjustment-{uuid4()}",
    )


@pytest.mark.asyncio
async def test_adjustments_are_attributed_append_only_and_idempotent(
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
        for reason, delta in (
            ("gain", "2"),
            ("found", "1"),
            ("loss", "-1"),
            ("damaged", "-2"),
            ("expired", "-1"),
        ):
            spec = adjustment_spec(
                company, branch, actor, item, warehouse, reason, delta
            )
            first = await repository.post_adjustment(session, spec=spec)
            duplicate = await repository.post_adjustment(session, spec=spec)
            assert first == duplicate
            movement = await session.get(StockMovement, first.movement_id)
            assert movement is not None
            assert movement.provenance_type == "inventory_adjustment"
            assert movement.provenance_id == first.id
        quantity = await repository.get_quantity(
            session,
            company_id=company.id,
            branch_id=branch.id,
            item_id=item.id,
            location_id=warehouse.id,
        )
        assert quantity.on_hand == Decimal("19.5")
        assert (
            await session.scalar(
                select(func.count())
                .select_from(InventoryAdjustment)
                .where(InventoryAdjustment.company_id == company.id)
            )
            == 5
        )

    async with factory() as session:
        adjustment = await session.scalar(
            select(InventoryAdjustment).where(
                InventoryAdjustment.company_id == company.id
            )
        )
        assert adjustment is not None
        with pytest.raises(DBAPIError, match="adjustment evidence is immutable"):
            await session.execute(
                update(InventoryAdjustment)
                .where(InventoryAdjustment.id == adjustment.id)
                .values(note="rewritten")
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_adjustment_validation_and_company_branch_isolation(
    inventory_fixture,  # noqa: F811
) -> None:
    factory, company, branch, other_branch, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    spec = adjustment_spec(company, branch, actor, item, warehouse, "gain", "1")
    async with factory() as session, session.begin():
        with pytest.raises(InventoryValidation, match="direction conflict"):
            await repository.post_adjustment(
                session, spec=replace(spec, reason="damaged")
            )
        with pytest.raises(InventoryNotFound, match="Company- and Branch-scoped"):
            await repository.post_adjustment(
                session,
                spec=replace(
                    spec,
                    branch_id=other_branch.id,
                    idempotency_key=f"isolated-{uuid4()}",
                ),
            )


@pytest.mark.asyncio
async def test_projection_reconciliation_uses_only_movement_evidence(
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
        await session.execute(
            update(InventoryQuantity)
            .where(
                InventoryQuantity.company_id == company.id,
                InventoryQuantity.item_id == item.id,
            )
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


@pytest.mark.asyncio
async def test_adjustment_cannot_impair_active_reservation(
    inventory_fixture,  # noqa: F811
) -> None:
    from app.inventory.contracts import CreateReservation

    factory, company, branch, _, actor = inventory_fixture
    repository, item, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
    async with factory() as session, session.begin():
        await repository.post_movement(
            session, spec=opening_spec(company, branch, actor, item, warehouse)
        )
        await repository.create_reservation(
            session,
            spec=CreateReservation(
                company_id=company.id,
                branch_id=branch.id,
                item_id=item.id,
                location_id=warehouse.id,
                quantity=Decimal(15),
                demand_type="manual_demand",
                demand_id=uuid4(),
                actor_user_id=actor.id,
                idempotency_key=f"reservation-{uuid4()}",
            ),
        )
        with pytest.raises(InventoryConflict, match="available quantity negative"):
            await repository.post_adjustment(
                session,
                spec=adjustment_spec(
                    company, branch, actor, item, warehouse, "loss", "-6"
                ),
            )
