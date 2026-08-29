import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from app.accounting.models import Journal
from app.accounts_payable.models import VendorBill
from app.events.models import BusinessEvent
from app.inventory.models import (
    InventoryItem,
    InventoryQuantity,
    StockLocation,
    StockMovement,
)
from app.purchasing.errors import (
    PurchasingConflict,
    PurchasingNotFound,
    PurchasingValidation,
)
from app.purchasing.models import (
    OperationalVendor,
    PurchaseOrder,
    ReplenishmentDecisionEvidence,
)
from app.purchasing.schemas import (
    ReplenishmentDecisionCommand,
    ReplenishmentTarget,
    ReplenishmentWorkbenchRequest,
    VendorCreate,
)
from app.purchasing.service import PurchasingService

pytest_plugins = ("tests.purchasing.test_purchasing_foundation",)

QUALIFICATION_PATH = (
    Path(__file__).parents[3]
    / "docs/architecture/purchasing/bank-pur-008-qualification.v1.json"
)


def test_bank_pur_008_qualification_artifact_is_canonical() -> None:
    payload = json.loads(QUALIFICATION_PATH.read_text())
    fingerprint = payload.pop("qualification_fingerprint")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    assert payload["implementation_sha"] == "e9483c9"
    assert payload["repair_sha"] == "a6af6ed6a9fbee0f12c13e3489012787275bd09d"
    assert payload["qualification_base_sha"] == (
        "aa28572ac5e3339937e81264420720dbea1ebd77"
    )
    assert payload["migration_revision"] == "b9s1o3q5t720"
    assert payload["state"] == "QUALIFIED_AWAITING_OWNER_ACCEPTANCE"
    assert payload["successor_gate"]["state"] == (
        "BLOCKED_PENDING_BANK_PUR_008_OWNER_ACCEPTANCE"
    )
    assert fingerprint == hashlib.sha256(canonical.encode()).hexdigest()


async def _recommendation_setup(purchasing_fixture):
    factory, company, other_company, branch, other_branch, preparer, approver = (
        purchasing_fixture
    )
    service = PurchasingService()
    async with factory() as session:
        vendor = await service.create_vendor(
            session,
            context=preparer,
            payload=VendorCreate(
                code=f"R1-{uuid4().hex[:8]}",
                display_name="R1 synthetic vendor",
                idempotency_key=f"r1-vendor-{uuid4()}",
            ),
        )
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"R1-{uuid4().hex[:8].upper()}",
            name="R1 synthetic item",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"R1{uuid4().hex[:8].upper()}",
            name="R1 synthetic location",
            location_type="warehouse",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        session.add_all([item, location])
        await session.flush()
        session.add(
            InventoryQuantity(
                company_id=company.id,
                branch_id=branch.id,
                item_id=item.id,
                location_id=location.id,
                on_hand=Decimal(2),
                reserved=Decimal(0),
            )
        )
    request = ReplenishmentWorkbenchRequest(
        as_of=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        targets=(
            ReplenishmentTarget(
                branch_id=branch.id,
                inventory_item_id=item.id,
                target_available_quantity=Decimal(7),
            ),
        ),
    )
    async with factory() as session:
        recommendation = (
            await service.replenishment_workbench(
                session, context=approver, payload=request
            )
        ).recommendations[0]
    return (
        factory,
        company,
        other_company,
        branch,
        other_branch,
        preparer,
        approver,
        service,
        vendor,
        item,
        request,
        recommendation,
    )


def _decision(
    *,
    branch_id: UUID,
    item_id: UUID,
    vendor_id: UUID,
    recommendation_as_of: datetime,
    recommendation_digest: str,
    key: str,
    decision: str = "approved",
) -> ReplenishmentDecisionCommand:
    approved = decision == "approved"
    return ReplenishmentDecisionCommand(
        branch_id=branch_id,
        inventory_item_id=item_id,
        recommendation_as_of=recommendation_as_of,
        target_available_quantity=Decimal(7),
        recommendation_digest=recommendation_digest,
        decision=decision,
        reason=f"R1 synthetic {decision}",
        approved_quantity=Decimal(5) if approved else None,
        vendor_id=vendor_id if approved else None,
        po_number=f"R1-{uuid4().hex[:10]}" if approved else None,
        currency="USD" if approved else None,
        unit_cost=Decimal("3.25") if approved else None,
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_replenishment_decision_evidence_is_database_immutable(
    purchasing_fixture,
) -> None:
    (
        factory,
        _,
        _,
        branch,
        _,
        _,
        approver,
        service,
        vendor,
        item,
        request,
        recommendation,
    ) = await _recommendation_setup(purchasing_fixture)
    command = _decision(
        branch_id=branch.id,
        item_id=item.id,
        vendor_id=vendor.id,
        recommendation_as_of=request.as_of,
        recommendation_digest=recommendation.evidence_digest,
        key=f"r1-immutable-{uuid4()}",
    )
    async with factory() as session:
        accepted = await service.decide_replenishment(
            session, context=approver, payload=command
        )

    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ReplenishmentDecisionEvidence)
                .where(ReplenishmentDecisionEvidence.id == accepted.id)
                .values(reason="prohibited rewrite")
            )
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ReplenishmentDecisionEvidence)
                .where(ReplenishmentDecisionEvidence.id == accepted.id)
                .values(
                    actor_user_id=uuid4(),
                    decided_at=accepted.decided_at + timedelta(seconds=1),
                    approval_evidence_digest="0" * 64,
                    purchase_order_id=None,
                )
            )
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                delete(ReplenishmentDecisionEvidence).where(
                    ReplenishmentDecisionEvidence.id == accepted.id
                )
            )
    async with factory() as session:
        stored = await session.get(ReplenishmentDecisionEvidence, accepted.id)
        assert stored is not None
        assert stored.reason == command.reason
        assert stored.actor_user_id == approver.user.id
        assert stored.approval_evidence_digest == accepted.approval_evidence_digest
        assert stored.purchase_order_id == accepted.purchase_order_id


@pytest.mark.asyncio
async def test_replenishment_decision_replay_staleness_and_atomic_boundaries(
    purchasing_fixture,
) -> None:
    (
        factory,
        _,
        _,
        branch,
        _,
        _,
        approver,
        service,
        vendor,
        item,
        request,
        recommendation,
    ) = await _recommendation_setup(purchasing_fixture)
    command = _decision(
        branch_id=branch.id,
        item_id=item.id,
        vendor_id=vendor.id,
        recommendation_as_of=request.as_of,
        recommendation_digest=recommendation.evidence_digest,
        key=f"r1-replay-{uuid4()}",
    )
    async with factory() as session:
        before = {
            model: await session.scalar(select(func.count()).select_from(model))
            for model in (InventoryQuantity, StockMovement, VendorBill, Journal)
        }
    async with factory() as session:
        first = await service.decide_replenishment(
            session, context=approver, payload=command
        )
    async with factory() as session:
        replay = await service.decide_replenishment(
            session, context=approver, payload=command
        )
        assert replay == first
        with pytest.raises(PurchasingConflict):
            await service.decide_replenishment(
                session,
                context=approver,
                payload=command.model_copy(
                    update={"decision": "rejected", "reason": "contradiction"}
                ),
            )
    async with factory() as session:
        after = {
            model: await session.scalar(select(func.count()).select_from(model))
            for model in (InventoryQuantity, StockMovement, VendorBill, Journal)
        }
        assert after == before
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PurchaseOrder)
                .where(PurchaseOrder.id == first.purchase_order_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.entity_id == first.id)
            )
            == 2
        )
    async with factory() as session, session.begin():
        quantity = await session.scalar(
            select(InventoryQuantity).where(InventoryQuantity.item_id == item.id)
        )
        assert quantity is not None
        quantity.on_hand = Decimal(1)
    async with factory() as session:
        before_decisions = await session.scalar(
            select(func.count()).select_from(ReplenishmentDecisionEvidence)
        )
        before_orders = await session.scalar(
            select(func.count()).select_from(PurchaseOrder)
        )
    async with factory() as session:
        with pytest.raises(
            PurchasingConflict, match="STALE_REPLENISHMENT_RECOMMENDATION"
        ):
            await service.decide_replenishment(
                session,
                context=approver,
                payload=command.model_copy(
                    update={"idempotency_key": f"r1-stale-{uuid4()}"}
                ),
            )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(ReplenishmentDecisionEvidence)
            )
            == before_decisions
        )
        assert (
            await session.scalar(select(func.count()).select_from(PurchaseOrder))
            == before_orders
        )


@pytest.mark.asyncio
async def test_replenishment_tenant_bindings_rejection_and_failure_atomicity(
    purchasing_fixture,
) -> None:
    (
        factory,
        _,
        other_company,
        branch,
        other_branch,
        preparer,
        approver,
        service,
        vendor,
        item,
        request,
        recommendation,
    ) = await _recommendation_setup(purchasing_fixture)
    async with factory() as session, session.begin():
        foreign_vendor = OperationalVendor(
            company_id=other_company.id,
            code=f"FOREIGN-{uuid4().hex[:8].upper()}",
            display_name="Foreign synthetic vendor",
            status="active",
            created_by_user_id=preparer.user.id,
        )
        foreign_item = InventoryItem(
            company_id=other_company.id,
            code=f"FOREIGN-{uuid4().hex[:8].upper()}",
            name="Foreign synthetic item",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        session.add_all([foreign_vendor, foreign_item])
        await session.flush()

    approved = _decision(
        branch_id=branch.id,
        item_id=item.id,
        vendor_id=vendor.id,
        recommendation_as_of=request.as_of,
        recommendation_digest=recommendation.evidence_digest,
        key=f"r1-binding-{uuid4()}",
    )
    async with factory() as session:
        before_decisions = await session.scalar(
            select(func.count()).select_from(ReplenishmentDecisionEvidence)
        )
        before_orders = await session.scalar(
            select(func.count()).select_from(PurchaseOrder)
        )
    async with factory() as session:
        with pytest.raises(PurchasingValidation, match="Active operational Vendor"):
            await service.decide_replenishment(
                session,
                context=approver,
                payload=approved.model_copy(
                    update={
                        "vendor_id": foreign_vendor.id,
                        "idempotency_key": f"r1-foreign-vendor-{uuid4()}",
                    }
                ),
            )
    async with factory() as session:
        with pytest.raises(PurchasingNotFound):
            await service.decide_replenishment(
                session,
                context=approver,
                payload=approved.model_copy(
                    update={
                        "branch_id": other_branch.id,
                        "idempotency_key": f"r1-foreign-branch-{uuid4()}",
                    }
                ),
            )
    async with factory() as session:
        with pytest.raises(PurchasingNotFound):
            await service.decide_replenishment(
                session,
                context=approver,
                payload=approved.model_copy(
                    update={
                        "inventory_item_id": foreign_item.id,
                        "idempotency_key": f"r1-foreign-item-{uuid4()}",
                    }
                ),
            )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(ReplenishmentDecisionEvidence)
            )
            == before_decisions
        )
        assert (
            await session.scalar(select(func.count()).select_from(PurchaseOrder))
            == before_orders
        )

    rejection = _decision(
        branch_id=branch.id,
        item_id=item.id,
        vendor_id=vendor.id,
        recommendation_as_of=request.as_of,
        recommendation_digest=recommendation.evidence_digest,
        key=f"r1-rejection-{uuid4()}",
        decision="rejected",
    )
    async with factory() as session:
        rejected = await service.decide_replenishment(
            session, context=approver, payload=rejection
        )
        replay = await service.decide_replenishment(
            session, context=approver, payload=rejection
        )
        assert replay == rejected
        assert rejected.purchase_order_id is None
        assert rejected.vendor_id is None
        assert rejected.approved_quantity is None
