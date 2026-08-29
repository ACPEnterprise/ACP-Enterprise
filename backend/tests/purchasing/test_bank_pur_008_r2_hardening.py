import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.events.models import BusinessEvent
from app.purchasing.errors import PurchasingConflict
from app.purchasing.models import PurchaseOrder, ReplenishmentDecisionEvidence
from app.purchasing.schemas import ReplenishmentDecisionCommand, VendorCreate
from app.purchasing.service import PurchasingService
from tests.purchasing.test_bank_pur_008_r1_qualification import (
    _decision,
    _recommendation_setup,
)

pytest_plugins = ("tests.purchasing.test_purchasing_foundation",)


async def _race_case(purchasing_fixture):
    setup = await _recommendation_setup(purchasing_fixture)
    factory, _, _, branch, _, preparer, approver, service, vendor, item, request, recommendation = setup
    async with factory() as session:
        alternate_vendor = await service.create_vendor(
            session,
            context=preparer,
            payload=VendorCreate(
                code=f"R2-{uuid4().hex[:8]}",
                display_name="R2 alternate vendor",
                idempotency_key=f"r2-vendor-{uuid4()}",
            ),
        )

    def command(suffix: str) -> ReplenishmentDecisionCommand:
        return _decision(
            branch_id=branch.id,
            item_id=item.id,
            vendor_id=vendor.id,
            recommendation_as_of=request.as_of,
            recommendation_digest=recommendation.evidence_digest,
            key=f"r2-{suffix}-{uuid4()}",
        )

    async def decide(payload: ReplenishmentDecisionCommand):
        async with factory() as session:
            return await service.decide_replenishment(
                session, context=approver, payload=payload
            )

    return factory, service, recommendation, alternate_vendor, command, decide


@pytest.mark.asyncio
async def test_equivalent_concurrent_approvals_recover_one_authority(
    purchasing_fixture,
) -> None:
    factory, _, recommendation, _, command, decide = await _race_case(
        purchasing_fixture
    )
    first_command, second_command = command("a"), command("b")
    first, second = await asyncio.gather(decide(first_command), decide(second_command))
    assert first.id == second.id
    assert first.purchase_order_id == second.purchase_order_id
    assert (await decide(second_command)).id == first.id
    async with factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(ReplenishmentDecisionEvidence).where(
                ReplenishmentDecisionEvidence.recommendation_digest
                == recommendation.evidence_digest
            )
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(PurchaseOrder).where(
                PurchaseOrder.id == first.purchase_order_id
            )
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(BusinessEvent).where(
                BusinessEvent.entity_id == first.id
            )
        ) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("contradiction", ("decision", "vendor", "quantity", "price"))
async def test_contradictory_concurrent_disposition_has_one_conflict(
    purchasing_fixture,
    contradiction: str,
) -> None:
    factory, _, recommendation, alternate_vendor, command, decide = await _race_case(
        purchasing_fixture
    )
    first, second = command("a"), command("b")
    if contradiction == "decision":
        second = second.model_copy(update={"decision": "rejected", "reason": "R1 synthetic rejected", "approved_quantity": None, "vendor_id": None, "po_number": None, "currency": None, "unit_cost": None})
    elif contradiction == "vendor":
        second = second.model_copy(update={"vendor_id": alternate_vendor.id})
    elif contradiction == "quantity":
        second = second.model_copy(update={"approved_quantity": Decimal(4)})
    else:
        second = second.model_copy(update={"unit_cost": Decimal("4.25")})
    results = await asyncio.gather(decide(first), decide(second), return_exceptions=True)
    winners = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [result for result in results if isinstance(result, PurchasingConflict)]
    assert len(winners) == len(conflicts) == 1
    async with factory() as session:
        decisions = (
            await session.scalars(
                select(ReplenishmentDecisionEvidence).where(
                    ReplenishmentDecisionEvidence.recommendation_digest
                    == recommendation.evidence_digest
                )
            )
        ).all()
        assert len(decisions) == 1
        event_count = await session.scalar(
            select(func.count()).select_from(BusinessEvent).where(
                BusinessEvent.entity_id == decisions[0].id
            )
        )
        assert event_count == (2 if decisions[0].decision == "approved" else 1)


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_not_reclassified(monkeypatch) -> None:
    service = PurchasingService()
    unrelated = IntegrityError("statement", {}, Exception("unrelated integrity"))

    async def fail(*args, **kwargs):
        raise unrelated

    monkeypatch.setattr(service, "_decide_replenishment_once", fail)
    with pytest.raises(IntegrityError) as raised:
        await service.decide_replenishment(object(), context=object(), payload=object())
    assert raised.value is unrelated
