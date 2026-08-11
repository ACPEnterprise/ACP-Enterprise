from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.events.models import BusinessEvent
from app.inventory.contracts import CreateStockLocation
from app.inventory.errors import InventoryNotFound
from app.inventory.schemas import TransferCreate
from app.inventory.service import InventoryService
from app.platform.company.membership_models import Membership
from app.platform.permissions.authorization import AuthorizationContext
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
    repository, _, warehouse, _ = await seed_foundation(
        factory, company, branch, actor
    )
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
