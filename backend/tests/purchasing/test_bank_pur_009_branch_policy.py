import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from app.accounting.models import Journal
from app.accounts_payable.models import VendorBill
from app.business_economics.models import CompanyFinancePolicyVersion
from app.events.models import BusinessEvent
from app.inventory.models import InventoryItem, StockMovement
from app.payments.models import PaymentIntent
from app.purchasing.errors import PurchasingConflict, PurchasingNotFound
from app.purchasing.models import (
    BranchPurchasingPolicy,
    BranchPurchasingPolicyRevision,
)
from app.purchasing.schemas import BranchPurchasingPolicyWrite
from app.purchasing.service import PurchasingService
from sqlalchemy import func, select

pytest_plugins = ("tests.purchasing.test_purchasing_foundation",)


async def _item(factory, company, actor):
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"POL-{uuid4().hex[:8].upper()}",
            name="Synthetic policy item",
            stocking_unit="each",
            status="active",
            created_by_user_id=actor.user.id,
            updated_by_user_id=actor.user.id,
        )
        session.add(item)
        await session.flush()
        return item


def _command(branch_id, item_id, key, *, target="8", version=None, status="active"):
    return BranchPurchasingPolicyWrite(
        branch_id=branch_id,
        inventory_item_id=item_id,
        target_available_quantity=Decimal(target),
        status=status,
        provenance_reference="operator-approved replenishment target",
        reason="Branch stock target reviewed",
        expected_version=version,
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_policy_is_company_branch_scoped_versioned_and_idempotent(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, other_branch, preparer, _ = purchasing_fixture
    service = PurchasingService()
    item = await _item(factory, company, preparer)
    command = _command(branch.id, item.id, "policy-create")

    async with factory() as session:
        created = await service.configure_branch_policy(
            session, context=preparer, payload=command
        )
    async with factory() as session:
        replay = await service.configure_branch_policy(
            session, context=preparer, payload=command
        )
        visible = await service.branch_policies(session, context=preparer)

    assert replay.id == created.id
    assert replay.version == 1
    assert len(replay.revisions) == 1
    assert visible == (replay,)
    assert replay.revisions[0].evidence_digest

    with pytest.raises(PurchasingConflict):
        async with factory() as session:
            await service.configure_branch_policy(
                session,
                context=preparer,
                payload=_command(branch.id, item.id, "policy-create", target="9"),
            )
    with pytest.raises(PurchasingNotFound):
        async with factory() as session:
            await service.configure_branch_policy(
                session,
                context=preparer,
                payload=_command(other_branch.id, item.id, "wrong-branch"),
            )


@pytest.mark.asyncio
async def test_policy_update_preserves_history_and_rejects_stale_version(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, _, preparer, _ = purchasing_fixture
    service = PurchasingService()
    item = await _item(factory, company, preparer)
    async with factory() as session:
        first = await service.configure_branch_policy(
            session,
            context=preparer,
            payload=_command(branch.id, item.id, "create-versioned"),
        )
    async with factory() as session:
        updated = await service.configure_branch_policy(
            session,
            context=preparer,
            payload=_command(
                branch.id,
                item.id,
                "update-versioned",
                target="12",
                version=first.version,
            ),
        )
    assert updated.version == 2
    assert updated.target_available_quantity == Decimal(12)
    assert [revision.target_available_quantity for revision in updated.revisions] == [
        Decimal(8),
        Decimal(12),
    ]
    with pytest.raises(PurchasingConflict):
        async with factory() as session:
            await service.configure_branch_policy(
                session,
                context=preparer,
                payload=_command(branch.id, item.id, "stale", version=1),
            )


@pytest.mark.asyncio
async def test_policy_has_no_downstream_domain_side_effects(purchasing_fixture) -> None:
    factory, company, _, branch, _, preparer, _ = purchasing_fixture
    service = PurchasingService()
    item = await _item(factory, company, preparer)
    models = (
        StockMovement,
        VendorBill,
        Journal,
        PaymentIntent,
        CompanyFinancePolicyVersion,
    )
    async with factory() as session:
        before = [
            await session.scalar(select(func.count()).select_from(model))
            for model in models
        ]
        policy_before = await session.scalar(
            select(func.count()).select_from(BranchPurchasingPolicy)
        )
        revision_before = await session.scalar(
            select(func.count()).select_from(BranchPurchasingPolicyRevision)
        )
        event_before = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(BusinessEvent.event_type == "purchasing.branch_policy.configured")
        )
    async with factory() as session:
        await service.configure_branch_policy(
            session,
            context=preparer,
            payload=_command(branch.id, item.id, "boundary"),
        )
    async with factory() as session:
        after = [
            await session.scalar(select(func.count()).select_from(model))
            for model in models
        ]
        policies = await session.scalar(
            select(func.count()).select_from(BranchPurchasingPolicy)
        )
        revisions = await session.scalar(
            select(func.count()).select_from(BranchPurchasingPolicyRevision)
        )
        events = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(BusinessEvent.event_type == "purchasing.branch_policy.configured")
        )
    assert after == before
    assert policies == policy_before + 1
    assert revisions == revision_before + 1
    assert events == event_before + 1


@pytest.mark.asyncio
async def test_competing_updates_cannot_both_apply(purchasing_fixture) -> None:
    factory, company, _, branch, _, preparer, _ = purchasing_fixture
    service = PurchasingService()
    item = await _item(factory, company, preparer)
    async with factory() as session:
        created = await service.configure_branch_policy(
            session,
            context=preparer,
            payload=_command(branch.id, item.id, "race-create"),
        )

    async def update(target: str, key: str):
        async with factory() as session:
            return await service.configure_branch_policy(
                session,
                context=preparer,
                payload=_command(
                    branch.id, item.id, key, target=target, version=created.version
                ),
            )

    outcomes = await asyncio.gather(
        update("9", "race-nine"), update("10", "race-ten"), return_exceptions=True
    )
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, PurchasingConflict) for item in outcomes) == 1
