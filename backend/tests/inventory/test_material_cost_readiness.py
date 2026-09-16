from uuid import uuid4

import pytest

from app.inventory.costing import MaterialCostingService
from app.inventory.models import InventoryItem, StockLocation
from app.purchasing.service import PurchasingService
from tests.purchasing.test_purchasing_foundation import (
    issued_order,
    purchasing_fixture,  # noqa: F401
    receipt,
)


@pytest.mark.asyncio
async def test_actual_receipt_cost_is_evidence_but_valuation_policy_remains_required(
    purchasing_fixture,  # noqa: F811
) -> None:
    factory, company, _, branch, _, preparer, approver = purchasing_fixture
    purchasing = PurchasingService()
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"COST-{uuid4().hex[:8].upper()}",
            name="Cost-qualified fitting",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"COST{uuid4().hex[:7].upper()}",
            name="Cost receipt warehouse",
            location_type="warehouse",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        session.add_all([item, location])
        await session.flush()
        item_id, location_id = item.id, location.id
    po_id, line_id, version = await issued_order(
        factory,
        branch,
        preparer,
        approver,
        quantity="4",
        inventory_item_id=item_id,
    )
    async with factory() as session:
        await purchasing.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version,
                line_id,
                "4",
                f"cost-readiness-{uuid4()}",
                receiving_location_id=location_id,
            ),
        )
    async with factory() as session:
        result = await MaterialCostingService().readiness(session, context=approver)

    evidence = next(row for row in result.evidence if row.inventory_item_id == item_id)
    readiness = next(
        row for row in result.readiness if row.inventory_item_id == item_id
    )
    assert evidence.authority_state == "ACTUAL_RECEIPT"
    assert evidence.accepted_quantity == 4
    assert evidence.unit_cost == 4
    assert evidence.currency == "USD"
    assert readiness.actual_receipt_cost_available is True
    assert readiness.on_hand_quantity == 4
    assert readiness.blockers == ("VALUATION_METHOD_POLICY_REQUIRED",)
