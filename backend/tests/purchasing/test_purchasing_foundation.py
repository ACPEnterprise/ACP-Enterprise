import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounting.models import Journal
from app.accounts_payable.models import AccountingVendor, VendorBill
from app.business_economics.models import CompanyFinancePolicyVersion
from app.core.config import settings
from app.events.models import BusinessEvent
from app.inventory.models import (
    InventoryItem,
    InventoryQuantity,
    MaterialIssue,
    StockLocation,
    StockMovement,
)
from app.main import app
from app.payments.models import PaymentIntent, Refund
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.purchasing.errors import (
    PurchasingConflict,
    PurchasingNotFound,
    PurchasingValidation,
)
from app.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderDiscrepancy,
    PurchaseOrderDispositionEvidence,
    PurchaseOrderIssuanceEvidence,
    PurchaseOrderRevision,
    PurchaseReturn,
    ReplenishmentDecisionEvidence,
)
from app.purchasing.schemas import (
    CreatePurchaseReturnCommand,
    DecidePurchaseOrderChangeCommand,
    PurchaseOrderChangeOperation,
    PurchaseOrderCreate,
    PurchaseOrderDispositionCommand,
    PurchaseOrderLineWrite,
    PurchaseOrderUpdate,
    PurchaseReturnTransitionCommand,
    ReceiptLineCommand,
    RecordReceiptCommand,
    ReplenishmentDecisionCommand,
    ReplenishmentTarget,
    ReplenishmentWorkbenchRequest,
    RequestPurchaseOrderChangeCommand,
    ResolveDiscrepancyCommand,
    TransitionCommand,
    VendorCreate,
    VendorUpdate,
)
from app.purchasing.service import PurchasingService


@pytest.mark.asyncio
async def test_replenishment_workbench_is_deterministic_isolated_and_read_only(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, other_branch, preparer, _ = purchasing_fixture
    service = PurchasingService()
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"REP-{uuid4().hex[:8].upper()}",
            name="Replenishment fitting",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"REP{uuid4().hex[:7].upper()}",
            name="Replenishment shelf",
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
                on_hand=Decimal(3),
                reserved=Decimal(1),
            )
        )
    request = ReplenishmentWorkbenchRequest(
        as_of=datetime(2026, 8, 28, 22, tzinfo=timezone.utc),
        targets=(
            ReplenishmentTarget(
                branch_id=branch.id,
                inventory_item_id=item.id,
                target_available_quantity=Decimal(10),
            ),
        ),
    )
    async with factory() as session:
        boundary_models = (
            InventoryItem,
            InventoryQuantity,
            StockMovement,
            MaterialIssue,
            AccountingVendor,
            VendorBill,
            Journal,
            PaymentIntent,
            Refund,
            CompanyFinancePolicyVersion,
        )
        before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in boundary_models
            ]
        )
        first = await service.replenishment_workbench(
            session, context=preparer, payload=request
        )
        replay = await service.replenishment_workbench(
            session, context=preparer, payload=request
        )
        recommendation = first.recommendations[0]
        after = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in boundary_models
            ]
        )
        assert first == replay
        assert first.evidence_digest == replay.evidence_digest
        assert recommendation.available_quantity == 2
        assert recommendation.open_purchase_order_quantity == 0
        assert recommendation.recommended_order_quantity == 8
        assert recommendation.recommendation_state == "recommend_order"
        assert after == before
        with pytest.raises(PurchasingNotFound):
            await service.replenishment_workbench(
                session,
                context=preparer,
                payload=request.model_copy(
                    update={
                        "targets": (
                            request.targets[0].model_copy(
                                update={"branch_id": other_branch.id}
                            ),
                        )
                    }
                ),
            )


@pytest.mark.asyncio
async def test_replenishment_approval_is_stale_safe_idempotent_and_links_one_po(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    async with factory() as session:
        vendor = await service.create_vendor(
            session,
            context=preparer,
            payload=VendorCreate(
                code=f"RV{uuid4().hex[:6]}",
                display_name="Approved replenishment vendor",
                idempotency_key=f"vendor-{uuid4()}",
            ),
        )
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"RA-{uuid4().hex[:8].upper()}",
            name="Approved item",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"RA{uuid4().hex[:7].upper()}",
            name="Approval shelf",
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
        as_of=datetime(2026, 8, 28, 23, tzinfo=timezone.utc),
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
    decision = ReplenishmentDecisionCommand(
        branch_id=branch.id,
        inventory_item_id=item.id,
        recommendation_as_of=request.as_of,
        target_available_quantity=Decimal(7),
        recommendation_digest=recommendation.evidence_digest,
        decision="approved",
        reason="Operator approved current evidence",
        approved_quantity=Decimal(5),
        vendor_id=vendor.id,
        po_number=f"REP-{uuid4().hex[:8]}",
        currency="USD",
        unit_cost=Decimal("3.25"),
        idempotency_key=f"approve-{uuid4()}",
    )
    async with factory() as session:
        first = await service.decide_replenishment(
            session, context=approver, payload=decision
        )
    async with factory() as session:
        replay = await service.decide_replenishment(
            session, context=approver, payload=decision
        )
        assert replay.id == first.id
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
    async with factory() as session:
        with pytest.raises(
            PurchasingConflict,
            match="Replenishment decision idempotency identity conflicts",
        ):
            await service.decide_replenishment(
                session,
                context=approver,
                payload=decision.model_copy(update={"reason": "Contradictory replay"}),
            )
    async with factory() as session:
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
        with pytest.raises(
            PurchasingConflict, match="STALE_REPLENISHMENT_RECOMMENDATION"
        ):
            await service.decide_replenishment(
                session,
                context=approver,
                payload=decision.model_copy(
                    update={"idempotency_key": f"stale-{uuid4()}"}
                ),
            )


async def replenishment_concurrency_case(purchasing_fixture):
    factory, company, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    vendors = []
    for suffix in ("A", "B"):
        async with factory() as session:
            vendors.append(
                await service.create_vendor(
                    session,
                    context=preparer,
                    payload=VendorCreate(
                        code=f"RC{suffix}{uuid4().hex[:5]}",
                        display_name=f"Race Vendor {suffix}",
                        idempotency_key=f"race-vendor-{suffix}-{uuid4()}",
                    ),
                )
            )
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"RC-{uuid4().hex[:8].upper()}",
            name="Replenishment race item",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"RC{uuid4().hex[:7].upper()}",
            name="Replenishment race shelf",
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
                on_hand=Decimal(0),
                reserved=Decimal(0),
            )
        )
    request = ReplenishmentWorkbenchRequest(
        as_of=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        targets=(
            ReplenishmentTarget(
                branch_id=branch.id,
                inventory_item_id=item.id,
                target_available_quantity=Decimal(5),
            ),
        ),
    )
    async with factory() as session:
        recommendation = (
            await service.replenishment_workbench(
                session, context=approver, payload=request
            )
        ).recommendations[0]

    def command(
        suffix: str,
        *,
        decision: str = "approved",
        vendor_index: int = 0,
        quantity: Decimal = Decimal(5),
        unit_cost: Decimal = Decimal(1),
    ) -> ReplenishmentDecisionCommand:
        approved = decision == "approved"
        return ReplenishmentDecisionCommand(
            branch_id=branch.id,
            inventory_item_id=item.id,
            recommendation_as_of=request.as_of,
            target_available_quantity=Decimal(5),
            recommendation_digest=recommendation.evidence_digest,
            decision=decision,
            reason="Concurrent independent qualification",
            approved_quantity=quantity if approved else None,
            vendor_id=vendors[vendor_index].id if approved else None,
            po_number=f"RACE-{suffix}-{uuid4().hex[:8]}" if approved else None,
            currency="USD" if approved else None,
            unit_cost=unit_cost if approved else None,
            idempotency_key=f"race-{suffix}-{uuid4()}",
        )

    async def decide(payload: ReplenishmentDecisionCommand):
        async with factory() as session:
            return await service.decide_replenishment(
                session, context=approver, payload=payload
            )

    return factory, service, recommendation, command, decide


@pytest.mark.asyncio
async def test_concurrent_equivalent_replenishment_approvals_recover_one_authority(
    purchasing_fixture,
) -> None:
    factory, _, recommendation, command, decide = await replenishment_concurrency_case(
        purchasing_fixture
    )
    first_command = command("A")
    second_command = command("B")
    first, second = await asyncio.gather(decide(first_command), decide(second_command))
    assert first.id == second.id
    assert first.purchase_order_id == second.purchase_order_id
    assert (await decide(second_command)).id == first.id
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ReplenishmentDecisionEvidence)
                .where(
                    ReplenishmentDecisionEvidence.recommendation_digest
                    == recommendation.evidence_digest
                )
            )
            == 1
        )
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "value"),
    (("decision", "rejected"), ("vendor_index", 1), ("quantity", Decimal(4)), ("unit_cost", Decimal(2))),
)
async def test_concurrent_contradictory_replenishment_disposition_is_conflict(
    purchasing_fixture,
    change,
    value,
) -> None:
    factory, _, recommendation, command, decide = await replenishment_concurrency_case(
        purchasing_fixture
    )
    first_command = command("A")
    second_command = command("B", **{change: value})
    results = await asyncio.gather(
        decide(first_command), decide(second_command), return_exceptions=True
    )
    winners = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [result for result in results if isinstance(result, PurchasingConflict)]
    assert len(winners) == 1
    assert len(conflicts) == 1
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ReplenishmentDecisionEvidence)
                .where(
                    ReplenishmentDecisionEvidence.recommendation_digest
                    == recommendation.evidence_digest
                )
            )
            == 1
        )
        decisions = (
            await session.scalars(
                select(ReplenishmentDecisionEvidence).where(
                    ReplenishmentDecisionEvidence.recommendation_digest
                    == recommendation.evidence_digest
                )
            )
        ).all()
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(BusinessEvent.entity_id == decisions[0].id)
        )
        assert event_count == (2 if decisions[0].decision == "approved" else 1)


@pytest.mark.asyncio
async def test_unrelated_replenishment_integrity_error_is_not_misclassified(
    monkeypatch,
) -> None:
    service = PurchasingService()
    unrelated = IntegrityError("statement", {}, Exception("unrelated integrity"))

    async def fail(*args, **kwargs):
        raise unrelated

    monkeypatch.setattr(service, "_decide_replenishment_once", fail)
    with pytest.raises(IntegrityError) as raised:
        await service.decide_replenishment(
            object(), context=object(), payload=object()
        )
    assert raised.value is unrelated


@pytest_asyncio.fixture
async def purchasing_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Purchasing Test",
            code=f"PUR{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        other_company = Company(
            name="Other Purchasing",
            code=f"OTH{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"P{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        other_branch = Branch(
            company=company,
            name="Other",
            code=f"Q{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=False,
        )
        preparer = User(
            normalized_email=f"prepare-{uuid4().hex}@example.test",
            first_name="Purchase",
            last_name="Preparer",
            display_name="Purchase Preparer",
            status="active",
        )
        approver = User(
            normalized_email=f"approve-{uuid4().hex}@example.test",
            first_name="Purchase",
            last_name="Approver",
            display_name="Purchase Approver",
            status="active",
        )
        session.add_all(
            [company, other_company, branch, other_branch, preparer, approver]
        )
        await session.flush()
        prep_membership = Membership(
            user_id=preparer.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
        )
        approval_membership = Membership(
            user_id=approver.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
        )
        session.add_all([prep_membership, approval_membership])
        await session.flush()

    def auth(user, membership):
        return AuthorizationContext(
            user=user,
            company=company,
            membership=membership,
            authorized_branches=(branch,),
            active_branch=branch,
            effective_roles=(),
            effective_permissions=(),
            credential_version=1,
            authorization_version=1,
        )

    try:
        yield (
            factory,
            company,
            other_company,
            branch,
            other_branch,
            auth(preparer, prep_membership),
            auth(approver, approval_membership),
        )
    finally:
        await engine.dispose()


def command(version: int, key: str, reason: str | None = None) -> TransitionCommand:
    return TransitionCommand(
        expected_version=version, idempotency_key=key, reason=reason
    )


@pytest.mark.asyncio
async def test_po_replay_revalidates_current_branch_authority(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, other_branch, preparer, _ = purchasing_fixture
    service = PurchasingService()
    other_branch_context = AuthorizationContext(
        user=preparer.user,
        company=preparer.company,
        membership=preparer.membership,
        authorized_branches=(other_branch,),
        active_branch=other_branch,
        effective_roles=preparer.effective_roles,
        effective_permissions=preparer.effective_permissions,
        credential_version=preparer.credential_version,
        authorization_version=preparer.authorization_version,
    )
    async with factory() as session:
        vendor = await service.create_vendor(
            session,
            context=preparer,
            payload=VendorCreate(
                code=f"REPLAY-{uuid4().hex[:8]}",
                display_name="Replay authority vendor",
                idempotency_key=f"replay-vendor-{uuid4()}",
            ),
        )
        order = await service.create_order(
            session,
            context=preparer,
            payload=PurchaseOrderCreate(
                branch_id=branch.id,
                vendor_id=vendor.id,
                po_number=f"REPLAY-{uuid4().hex[:8]}",
                currency="USD",
                idempotency_key=f"replay-po-{uuid4()}",
            ),
        )
        original_version = order.version
        payload = PurchaseOrderUpdate(
            expected_version=original_version,
            vendor_id=vendor.id,
            expected_date=None,
            idempotency_key=f"replay-update-{uuid4()}",
        )
        updated = await service.update_order(
            session,
            context=preparer,
            po_id=order.id,
            payload=payload,
        )
        assert updated.version == original_version + 1

    async with factory() as session:
        with pytest.raises(PurchasingNotFound, match="Purchasing Branch was not found"):
            await service.update_order(
                session,
                context=other_branch_context,
                po_id=order.id,
                payload=payload,
            )


@pytest.mark.asyncio
async def test_vendor_identity_is_company_owned_idempotent_and_concurrent(
    purchasing_fixture,
) -> None:
    factory, company, _, _, _, preparer, _ = purchasing_fixture
    service = PurchasingService()
    payload = VendorCreate(
        code="supply-1",
        display_name="Supply House",
        legal_name="Supply House LLC",
        contact_reference="contact-ref-1",
        idempotency_key="vendor-create-1",
    )
    async def create():
        async with factory() as session:
            return await service.create_vendor(
                session, context=preparer, payload=payload
            )

    first, concurrent_replay = await asyncio.gather(create(), create())
    assert concurrent_replay.id == first.id
    async with factory() as session:
        replay = await service.create_vendor(session, context=preparer, payload=payload)
        first_id = first.id
        assert (
            replay.id == first.id
            and replay.company_id == company.id
            and replay.code == "SUPPLY-1"
        )
        with pytest.raises(PurchasingConflict):
            await service.create_vendor(
                session,
                context=preparer,
                payload=payload.model_copy(update={"display_name": "Contradiction"}),
            )
        with pytest.raises(PurchasingConflict):
            await service.update_vendor(
                session,
                context=preparer,
                vendor_id=first_id,
                payload=VendorUpdate(
                    expected_version=99,
                    display_name="Supply",
                    legal_name=None,
                    contact_reference=None,
                    status="active",
                    idempotency_key="vendor-update-stale",
                ),
            )


@pytest.mark.asyncio
async def test_po_lifecycle_sod_immutable_issuance_and_nonmutation(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    async with factory() as session:
        before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (StockMovement, AccountingVendor, VendorBill, Journal)
            ]
        )
    async with factory() as session:
        vendor = await service.create_vendor(
            session,
            context=preparer,
            payload=VendorCreate(
                code="vendor-2", display_name="Vendor Two", idempotency_key="vendor-2"
            ),
        )
        order = await service.create_order(
            session,
            context=preparer,
            payload=PurchaseOrderCreate(
                branch_id=branch.id,
                vendor_id=vendor.id,
                po_number="po-100",
                currency="USD",
                idempotency_key="po-100",
            ),
        )
        line = await service.add_line(
            session,
            context=preparer,
            po_id=order.id,
            payload=PurchaseOrderLineWrite(
                expected_po_version=order.version,
                description="Non-catalog fitting",
                quantity=Decimal("2.5"),
                unit="each",
                unit_cost=Decimal("4.2500"),
                idempotency_key="po-100-line",
            ),
        )
        assert line.extended_cost == Decimal("10.6250000000")
        order = await service.transition(
            session,
            context=preparer,
            po_id=order.id,
            target="submit",
            payload=command(order.version, "po-100-submit"),
        )
        order_id = order.id
        submitted_version = order.version
    async with factory() as session:
        with pytest.raises(PurchasingValidation):
            await service.transition(
                session,
                context=preparer,
                po_id=order_id,
                target="approve",
                payload=command(submitted_version, "po-100-self-approve"),
            )
    async with factory() as session:
        order = await service.transition(
            session,
            context=approver,
            po_id=order_id,
            target="approve",
            payload=command(submitted_version, "po-100-approve"),
        )
        order = await service.transition(
            session,
            context=approver,
            po_id=order.id,
            target="issue",
            payload=command(order.version, "po-100-issue"),
        )
        issued_version = order.version
        replay = await service.transition(
            session,
            context=approver,
            po_id=order.id,
            target="issue",
            payload=command(issued_version - 1, "po-100-issue"),
        )
        assert replay.id == order.id and replay.version == issued_version
    async with factory() as session:
        evidence = await session.scalar(
            select(PurchaseOrderIssuanceEvidence).where(
                PurchaseOrderIssuanceEvidence.purchase_order_id == order_id
            )
        )
        assert evidence is not None and len(evidence.digest) == 64
        assert evidence.snapshot["vendor"]["display_name"] == "Vendor Two"
        after = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (StockMovement, AccountingVendor, VendorBill, Journal)
            ]
        )
        assert after == before
        event_types = set(
            (
                await session.scalars(
                    select(BusinessEvent.event_type).where(
                        BusinessEvent.entity_id == order_id
                    )
                )
            ).all()
        )
        assert {
            "purchasing.purchase_order_created",
            "purchasing.purchase_order_submitted",
            "purchasing.purchase_order_approved",
            "purchasing.purchase_order_issued",
        }.issubset(event_types)


@pytest.mark.asyncio
async def test_branch_isolation_and_explicit_nonreceipt_cancellation(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, other_branch, preparer, approver = purchasing_fixture
    service = PurchasingService()
    async with factory() as session:
        vendor = await service.create_vendor(
            session,
            context=preparer,
            payload=VendorCreate(
                code="vendor-3", display_name="Vendor Three", idempotency_key="vendor-3"
            ),
        )
        with pytest.raises(PurchasingNotFound):
            await service.create_order(
                session,
                context=preparer,
                payload=PurchaseOrderCreate(
                    branch_id=other_branch.id,
                    vendor_id=vendor.id,
                    po_number="hidden",
                    currency="USD",
                    idempotency_key="hidden-po",
                ),
            )
        cancelled = await service.create_order(
            session,
            context=preparer,
            payload=PurchaseOrderCreate(
                branch_id=branch.id,
                vendor_id=vendor.id,
                po_number="po-cancel",
                currency="USD",
                idempotency_key="po-cancel",
            ),
        )
        cancellation = await service.terminal_disposition(
            session,
            context=approver,
            po_id=cancelled.id,
            action="cancel",
            payload=PurchaseOrderDispositionCommand(
                expected_po_version=cancelled.version,
                expected_effective_revision=cancelled.effective_revision,
                reason="No longer required",
                confirm_terminal_action=True,
                idempotency_key="po-cancel-action",
            ),
        )
        assert cancellation.disposition == "canceled_before_receipt"
        order = await service.create_order(
            session,
            context=preparer,
            payload=PurchaseOrderCreate(
                branch_id=branch.id,
                vendor_id=vendor.id,
                po_number="po-close",
                currency="USD",
                idempotency_key="po-close",
            ),
        )
        await service.add_line(
            session,
            context=preparer,
            po_id=order.id,
            payload=PurchaseOrderLineWrite(
                expected_po_version=order.version,
                description="Close test",
                quantity=1,
                unit="each",
                unit_cost=1,
                idempotency_key="po-close-line",
            ),
        )
        order = await service.transition(
            session,
            context=preparer,
            po_id=order.id,
            target="submit",
            payload=command(order.version, "po-close-submit"),
        )
        order = await service.transition(
            session,
            context=approver,
            po_id=order.id,
            target="approve",
            payload=command(order.version, "po-close-approve"),
        )
        order = await service.transition(
            session,
            context=approver,
            po_id=order.id,
            target="issue",
            payload=command(order.version, "po-close-issue"),
        )
        cancellation = await service.terminal_disposition(
            session,
            context=approver,
            po_id=order.id,
            action="cancel",
            payload=PurchaseOrderDispositionCommand(
                expected_po_version=order.version,
                expected_effective_revision=order.effective_revision,
                reason="Owner-authorized non-receipt cancellation",
                confirm_terminal_action=True,
                idempotency_key="po-close-action",
            ),
        )
        assert cancellation.disposition == "canceled_before_receipt"


@pytest.mark.asyncio
async def test_purchasing_api_requires_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/purchasing")
    assert response.status_code in {401, 403}


async def issued_order(
    factory,
    branch,
    preparer,
    approver,
    *,
    quantity: str = "10",
    inventory_item_id=None,
):
    service = PurchasingService()
    async with factory() as session:
        vendor = await service.create_vendor(
            session,
            context=preparer,
            payload=VendorCreate(
                code=f"vendor-{uuid4().hex[:8]}",
                display_name="Receipt Vendor",
                idempotency_key=f"vendor-{uuid4()}",
            ),
        )
        order = await service.create_order(
            session,
            context=preparer,
            payload=PurchaseOrderCreate(
                branch_id=branch.id,
                vendor_id=vendor.id,
                po_number=f"PO-{uuid4().hex[:8]}",
                currency="USD",
                idempotency_key=f"po-{uuid4()}",
            ),
        )
        line = await service.add_line(
            session,
            context=preparer,
            po_id=order.id,
            payload=PurchaseOrderLineWrite(
                expected_po_version=order.version,
                description="Copper fitting",
                quantity=Decimal(quantity),
                unit="each",
                unit_cost=Decimal(4),
                inventory_item_id=inventory_item_id,
                idempotency_key=f"line-{uuid4()}",
            ),
        )
        order = await service.transition(
            session,
            context=preparer,
            po_id=order.id,
            target="submit",
            payload=command(order.version, f"submit-{uuid4()}"),
        )
        order = await service.transition(
            session,
            context=approver,
            po_id=order.id,
            target="approve",
            payload=command(order.version, f"approve-{uuid4()}"),
        )
        order = await service.transition(
            session,
            context=approver,
            po_id=order.id,
            target="issue",
            payload=command(order.version, f"issue-{uuid4()}"),
        )
        return order.id, line.id, order.version


@pytest.mark.asyncio
async def test_issued_po_change_is_versioned_idempotent_and_stale_safe(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    request = RequestPurchaseOrderChangeCommand(
        expected_po_version=version,
        base_revision=1,
        change_identity="CO-1",
        reason="Vendor confirmed increased quantity",
        idempotency_key="co-request-1",
        changes=(
            PurchaseOrderChangeOperation(
                operation="set_quantity", line_id=line_id, quantity=Decimal(12)
            ),
        ),
    )
    async with factory() as session:
        change = await service.request_change(
            session, context=preparer, po_id=po_id, payload=request
        )
        replay = await service.request_change(
            session, context=preparer, po_id=po_id, payload=request
        )
        assert replay.id == change.id and replay.status == "requested"
        change_id = change.id
        with pytest.raises(PurchasingConflict):
            await service.request_change(
                session,
                context=preparer,
                po_id=po_id,
                payload=request.model_copy(update={"reason": "contradiction"}),
            )
    decision = DecidePurchaseOrderChangeCommand(
        expected_po_version=version,
        expected_base_revision=1,
        idempotency_key="co-approve-1",
    )
    async with factory() as session:
        with pytest.raises(PurchasingValidation):
            await service.decide_change(
                session,
                context=preparer,
                po_id=po_id,
                change_id=change_id,
                action="approve",
                payload=decision,
            )
    async with factory() as session:
        approved = await service.decide_change(
            session,
            context=approver,
            po_id=po_id,
            change_id=change_id,
            action="approve",
            payload=decision,
        )
        assert approved.status == "approved" and approved.effective_revision == 2
        item = await service.get_order(session, context=preparer, po_id=po_id)
        assert item.effective_revision == 2 and item.lines[0].quantity == Decimal(12)
        assert [revision.revision_number for revision in item.revisions] == [1, 2]
        assert item.revisions[0].effective_snapshot["lines"][0]["quantity"] == "10"
        assert (
            await session.scalar(
                select(func.count()).select_from(PurchaseOrderRevision)
            )
            >= 2
        )
    async with factory() as session:
        with pytest.raises(PurchasingConflict):
            await service.request_change(
                session,
                context=preparer,
                po_id=po_id,
                payload=request.model_copy(
                    update={
                        "idempotency_key": "co-stale",
                        "expected_po_version": version,
                        "base_revision": 1,
                        "change_identity": "CO-STALE",
                    }
                ),
            )


def price_change(
    version: int,
    line_id,
    key: str,
    *,
    base_revision: int = 1,
    unit_cost: str = "6.25",
) -> RequestPurchaseOrderChangeCommand:
    return RequestPurchaseOrderChangeCommand(
        expected_po_version=version,
        base_revision=base_revision,
        change_identity=f"CO-{key}",
        reason="Vendor supplied a revised unit price",
        idempotency_key=f"request-{key}",
        changes=(
            PurchaseOrderChangeOperation(
                operation="set_unit_cost",
                line_id=line_id,
                unit_cost=Decimal(unit_cost),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_pre_receipt_price_change_is_authorized_and_versioned(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        requested = await service.request_change(
            session,
            context=preparer,
            po_id=po_id,
            payload=price_change(version, line_id, "PRE-RECEIPT"),
        )
        change_id = requested.id
    async with factory() as session:
        approved = await service.decide_change(
            session,
            context=approver,
            po_id=po_id,
            change_id=change_id,
            action="approve",
            payload=DecidePurchaseOrderChangeCommand(
                expected_po_version=version,
                expected_base_revision=1,
                idempotency_key="approve-pre-receipt",
            ),
        )
        order = await service.get_order(session, context=approver, po_id=po_id)
        assert approved.status == "approved"
        assert approved.downstream_reconciliation_required is False
        assert order.effective_revision == 2
        assert order.lines[0].unit_cost == Decimal("6.25")
        assert order.revisions[0].effective_snapshot["lines"][0]["unit_cost"] == "4"


@pytest.mark.parametrize("accepted,rejected", [("1", "0"), ("10", "0")])
@pytest.mark.asyncio
async def test_accepted_receiving_blocks_price_change_without_side_effects(
    purchasing_fixture, accepted: str, rejected: str
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version, line_id, accepted, f"PRICE-{accepted}", rejected=rejected
            ),
        )
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        current_version = order.version
    async with factory() as session:
        requested = await service.request_change(
            session,
            context=preparer,
            po_id=po_id,
            payload=price_change(current_version, line_id, f"POST-{accepted}"),
        )
        before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (
                    InventoryItem,
                    StockMovement,
                    MaterialIssue,
                    AccountingVendor,
                    VendorBill,
                    Journal,
                    PaymentIntent,
                    Refund,
                    CompanyFinancePolicyVersion,
                )
            ]
        )
        revision_count = await session.scalar(
            select(func.count())
            .select_from(PurchaseOrderRevision)
            .where(PurchaseOrderRevision.purchase_order_id == po_id)
        )
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(BusinessEvent.entity_id == requested.id)
        )
        change_id = requested.id
        await session.rollback()
        with pytest.raises(
            PurchasingValidation, match="POST_RECEIPT_PRICE_CHANGE_POLICY_REQUIRED"
        ):
            await service.decide_change(
                session,
                context=approver,
                po_id=po_id,
                change_id=change_id,
                action="approve",
                payload=DecidePurchaseOrderChangeCommand(
                    expected_po_version=current_version,
                    expected_base_revision=1,
                    idempotency_key=f"approve-post-{accepted}",
                ),
            )
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        change = await service.repository.change_order(
            session, order.company_id, change_id
        )
        after = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (
                    InventoryItem,
                    StockMovement,
                    MaterialIssue,
                    AccountingVendor,
                    VendorBill,
                    Journal,
                    PaymentIntent,
                    Refund,
                    CompanyFinancePolicyVersion,
                )
            ]
        )
        assert after == before
        assert order.effective_revision == 1
        assert order.lines[0].unit_cost == Decimal("4.0000")
        assert change is not None and change.status == "requested"
        assert change.downstream_reconciliation_required is False
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PurchaseOrderRevision)
                .where(PurchaseOrderRevision.purchase_order_id == po_id)
            )
            == revision_count
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.entity_id == change_id)
            )
            == event_count
        )


@pytest.mark.asyncio
async def test_rejected_only_receipt_does_not_block_price_change(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version,
                line_id,
                "0",
                "PRICE-REJECTED-ONLY",
                rejected="1",
                category="damaged_item",
            ),
        )
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        current_version = order.version
    async with factory() as session:
        requested = await service.request_change(
            session,
            context=preparer,
            po_id=po_id,
            payload=price_change(current_version, line_id, "REJECTED-ONLY"),
        )
        change_id = requested.id
    async with factory() as session:
        await service.decide_change(
            session,
            context=approver,
            po_id=po_id,
            change_id=change_id,
            action="approve",
            payload=DecidePurchaseOrderChangeCommand(
                expected_po_version=current_version,
                expected_base_revision=1,
                idempotency_key="approve-rejected-only",
            ),
        )
        order = await service.get_order(session, context=approver, po_id=po_id)
        assert order.lines[0].unit_cost == Decimal("6.25")


def receipt(
    version: int,
    line_id,
    accepted: str,
    key: str,
    *,
    rejected: str = "0",
    category: str | None = None,
    receiving_location_id=None,
):
    return RecordReceiptCommand(
        expected_po_version=version,
        receiving_event_identity=f"event-{key}",
        received_at=datetime.now(timezone.utc),
        effective_date=datetime.now(timezone.utc).date(),
        idempotency_key=key,
        receiving_location_id=receiving_location_id,
        lines=(
            ReceiptLineCommand(
                purchase_order_line_id=line_id,
                accepted_quantity=Decimal(accepted),
                rejected_quantity=Decimal(rejected),
                discrepancy_category=category,
                observed_condition="Package visibly damaged" if category else None,
            ),
        ),
    )


def disposition(
    version: int, revision: int, key: str, reason: str
) -> PurchaseOrderDispositionCommand:
    return PurchaseOrderDispositionCommand(
        expected_po_version=version,
        expected_effective_revision=revision,
        reason=reason,
        confirm_terminal_action=True,
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_inventory_receiving_posts_one_native_movement_and_replay_is_safe(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"REC-{uuid4().hex[:8].upper()}",
            name="Receipt-bound fitting",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"REC{uuid4().hex[:7].upper()}",
            name="Receiving dock",
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
        inventory_item_id=item_id,
    )
    command = receipt(
        version,
        line_id,
        "4",
        "inventory-receipt",
        receiving_location_id=location_id,
    )
    async with factory() as session:
        boundary_before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (VendorBill, Journal, PaymentIntent, Refund)
            ]
        )
    async def apply_receipt():
        async with factory() as session:
            return await service.record_receipt(
                session, context=approver, po_id=po_id, payload=command
            )

    first, replay = await asyncio.gather(apply_receipt(), apply_receipt())
    async with factory() as session:
        reconciliation = await service.receiving_reconciliation(
            session, context=approver, po_id=po_id
        )
        movements = (
            await session.scalars(
                select(StockMovement).where(
                    StockMovement.provenance_type == "purchase_order_receipt_line",
                    StockMovement.company_id == company.id,
                )
            )
        ).all()
        quantity = await session.scalar(
            select(InventoryQuantity).where(
                InventoryQuantity.company_id == company.id,
                InventoryQuantity.item_id == item_id,
                InventoryQuantity.location_id == location_id,
            )
        )
        boundary_counts = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (VendorBill, Journal, PaymentIntent, Refund)
            ]
        )
    assert replay.id == first.id
    assert first.inventory_application_state == "applied"
    assert len(movements) == 1
    assert movements[0].movement_type == "purchase_receipt"
    assert movements[0].unit_cost == Decimal(4)
    assert movements[0].valuation_method == "po_cost_evidence_unposted"
    assert quantity is not None and quantity.on_hand == Decimal(4)
    assert boundary_counts == boundary_before
    assert reconciliation.lines[0].reconciliation_state == "partial"
    assert reconciliation.lines[0].bill_state == "missing_bill"
    assert reconciliation.lines[0].inventory_received_quantity == Decimal(4)


@pytest.mark.asyncio
async def test_inventory_receiving_fails_closed_for_unmapped_item_or_wrong_branch(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, other_branch, preparer, approver = purchasing_fixture
    service = PurchasingService()
    async with factory() as session, session.begin():
        wrong_location = StockLocation(
            company_id=company.id,
            branch_id=other_branch.id,
            code=f"BAD{uuid4().hex[:7].upper()}",
            name="Wrong receiving dock",
            location_type="warehouse",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        correct_location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"OK{uuid4().hex[:8].upper()}",
            name="Correct receiving dock",
            location_type="warehouse",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        session.add_all([wrong_location, correct_location])
        await session.flush()
        wrong_location_id, correct_location_id = wrong_location.id, correct_location.id
    po_id, line_id, version = await issued_order(
        factory, branch, preparer, approver
    )
    async with factory() as session:
        with pytest.raises(PurchasingValidation, match="RECEIVING_LOCATION_NOT_FOUND"):
            await service.record_receipt(
                session,
                context=approver,
                po_id=po_id,
                payload=receipt(
                    version,
                    line_id,
                    "1",
                    "unmapped-item",
                    receiving_location_id=wrong_location_id,
                ),
            )
    async with factory() as session:
        with pytest.raises(PurchasingValidation, match="UNKNOWN_INVENTORY_ITEM"):
            await service.record_receipt(
                session,
                context=approver,
                po_id=po_id,
                payload=receipt(
                    version,
                    line_id,
                    "1",
                    "unmapped-item-valid-location",
                    receiving_location_id=correct_location_id,
                ),
            )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.company_id == company.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_physical_purchase_return_posts_one_inverse_inventory_movement(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company.id,
            code=f"RTN-{uuid4().hex[:8].upper()}",
            name="Return-bound fitting",
            stocking_unit="each",
            status="active",
            created_by_user_id=preparer.user.id,
            updated_by_user_id=preparer.user.id,
        )
        location = StockLocation(
            company_id=company.id,
            branch_id=branch.id,
            code=f"RTN{uuid4().hex[:7].upper()}",
            name="Return dock",
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
        quantity="3",
        inventory_item_id=item_id,
    )
    async with factory() as session:
        received = await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version,
                line_id,
                "3",
                "return-source-inventory",
                receiving_location_id=location_id,
            ),
        )
        order = await service.get_order(session, context=approver, po_id=po_id)
        receipt_line = (
            await service.repository.receipt_lines(
                session, company.id, received.id
            )
        )[0]
        receipt_id, receipt_line_id = received.id, receipt_line.id
        await session.rollback()
        purchase_return = await service.create_purchase_return(
            session,
            context=approver,
            po_id=po_id,
            payload=return_command(
                order.version,
                receipt_id,
                receipt_line_id,
                "1",
                "inventory-return",
                authorization_required=False,
            ),
        )
        ready = await service.transition_purchase_return(
            session,
            context=approver,
            po_id=po_id,
            return_id=purchase_return.id,
            action="mark_ready",
            payload=return_transition(
                order.version + 1,
                purchase_return.version,
                "inventory-return-ready",
            ),
        )
        returned = await service.transition_purchase_return(
            session,
            context=approver,
            po_id=po_id,
            return_id=ready.id,
            action="mark_returned",
            payload=return_transition(
                order.version + 2,
                ready.version,
                "inventory-return-physical",
            ),
        )
        return_movement_id = returned.inventory_movement_id
    async with factory() as session:
        movements = (
            await session.scalars(
                select(StockMovement)
                .where(StockMovement.company_id == company.id)
                .order_by(StockMovement.posted_at)
            )
        ).all()
        quantity = await session.scalar(
            select(InventoryQuantity).where(
                InventoryQuantity.company_id == company.id,
                InventoryQuantity.item_id == item_id,
                InventoryQuantity.location_id == location_id,
            )
        )
    assert [movement.movement_type for movement in movements] == [
        "purchase_receipt",
        "purchase_return",
    ]
    assert return_movement_id == movements[1].id
    assert movements[1].reversal_of_id == movements[0].id
    assert quantity is not None and quantity.on_hand == Decimal(2)


@pytest.mark.asyncio
async def test_fully_satisfied_disposition_is_evidenced_and_idempotent(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(version, line_id, "10", "complete-receipt"),
        )
    async with factory() as session:
        item = await service.get_order(session, context=approver, po_id=po_id)
        payload = disposition(
            item.version,
            item.effective_revision,
            "complete-po",
            "All effective quantities received",
        )
    async with factory() as session:
        completed = await service.terminal_disposition(
            session, context=approver, po_id=po_id, action="complete", payload=payload
        )
        replay = await service.terminal_disposition(
            session, context=approver, po_id=po_id, action="complete", payload=payload
        )
        assert replay.id == completed.id
        assert completed.disposition == "fully_satisfied"
        assert len(completed.evidence_digest) == 64
    async with factory() as session:
        item = await service.get_order(session, context=approver, po_id=po_id)
        assert item.status == "closed" and item.disposition is not None
        assert item.lines[0].outstanding_quantity == Decimal(0)
    async with factory() as session:
        with pytest.raises(PurchasingConflict):
            await service.terminal_disposition(
                session,
                context=approver,
                po_id=po_id,
                action="complete",
                payload=payload.model_copy(update={"reason": "contradiction"}),
            )
    async with factory() as session:
        report = await service.vendor_performance_evidence(
            session, context=approver, vendor_id=item.vendor_id
        )
    assert any(
        evidence.evidence_type == "fulfillment.receipt_state"
        and evidence.value == "fully_received"
        for evidence in report.evidence
    )


@pytest.mark.asyncio
async def test_unsatisfied_completion_fails_and_partial_remainder_cancel_is_explicit(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        with pytest.raises(PurchasingValidation):
            await service.terminal_disposition(
                session,
                context=approver,
                po_id=po_id,
                action="complete",
                payload=disposition(
                    version, 1, "not-complete", "Incorrect completion attempt"
                ),
            )
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(version, line_id, "4", "partial-before-cancel"),
        )
    async with factory() as session:
        item = await service.get_order(session, context=approver, po_id=po_id)
    async with factory() as session:
        canceled = await service.terminal_disposition(
            session,
            context=approver,
            po_id=po_id,
            action="cancel",
            payload=disposition(
                item.version, 1, "cancel-remainder", "Vendor cannot fulfill remainder"
            ),
        )
        assert canceled.disposition == "remainder_canceled"
        assert canceled.quantity_evidence[0]["accepted_received_quantity"] == "4.000000"
        assert Decimal(
            str(canceled.quantity_evidence[0]["canceled_remainder_quantity"])
        ) == Decimal(6)
    async with factory() as session:
        item = await service.get_order(session, context=approver, po_id=po_id)
        assert item.lines[0].quantity == Decimal(10)
        assert item.lines[0].cumulative_accepted_quantity == Decimal(4)
        assert item.lines[0].outstanding_quantity == Decimal(0)


@pytest.mark.asyncio
async def test_prior_change_order_line_cancellation_is_quantified_at_disposition(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        requested = await service.request_change(
            session,
            context=preparer,
            po_id=po_id,
            payload=RequestPurchaseOrderChangeCommand(
                expected_po_version=version,
                base_revision=1,
                change_identity="CO-CANCEL-PRIOR",
                reason="Vendor cannot supply this line",
                idempotency_key="request-cancel-prior",
                changes=(
                    PurchaseOrderChangeOperation(
                        operation="cancel_line", line_id=line_id
                    ),
                ),
            ),
        )
    async with factory() as session:
        await service.decide_change(
            session,
            context=approver,
            po_id=po_id,
            change_id=requested.id,
            action="approve",
            payload=DecidePurchaseOrderChangeCommand(
                expected_po_version=version,
                expected_base_revision=1,
                idempotency_key="approve-cancel-prior",
            ),
        )
        order = await service.get_order(session, context=approver, po_id=po_id)
        assert order.lines[0].is_cancelled is True
        assert order.lines[0].outstanding_quantity == Decimal(0)
    completion = disposition(
        order.version,
        order.effective_revision,
        "complete-canceled-line",
        "Incorrect satisfaction attempt",
    )
    async with factory() as session:
        with pytest.raises(PurchasingValidation, match="not fully satisfied"):
            await service.terminal_disposition(
                session,
                context=approver,
                po_id=po_id,
                action="complete",
                payload=completion,
            )
    cancellation = disposition(
        order.version,
        order.effective_revision,
        "terminal-canceled-line",
        "Preserve prior line cancellation",
    )
    async with factory() as session:
        result = await service.terminal_disposition(
            session,
            context=approver,
            po_id=po_id,
            action="cancel",
            payload=cancellation,
        )
        replay = await service.terminal_disposition(
            session,
            context=approver,
            po_id=po_id,
            action="cancel",
            payload=cancellation,
        )
        line_evidence = result.quantity_evidence[0]
        assert replay.id == result.id
        assert result.disposition == "canceled_before_receipt"
        assert Decimal(str(line_evidence["effective_ordered_quantity"])) == 10
        assert Decimal(str(line_evidence["accepted_received_quantity"])) == 0
        assert Decimal(str(line_evidence["canceled_remainder_quantity"])) == 10
        assert Decimal(str(line_evidence["accepted_received_quantity"])) + Decimal(
            str(line_evidence["canceled_remainder_quantity"])
        ) == Decimal(str(line_evidence["effective_ordered_quantity"]))
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == po_id,
                BusinessEvent.event_type == "purchasing.purchase_order_cancelled",
            )
        )
        assert event_count == 1


@pytest.mark.asyncio
async def test_mixed_line_terminal_evidence_reconciles_every_effective_quantity(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, first_line_id, version = await issued_order(
        factory, branch, preparer, approver
    )
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(version, first_line_id, "10", "mixed-full-receipt"),
        )
    async with factory() as session:
        order = await service.get_order(session, context=preparer, po_id=po_id)
        add_version = order.version
        add_revision = order.effective_revision
    async with factory() as session:
        added = await service.request_change(
            session,
            context=preparer,
            po_id=po_id,
            payload=RequestPurchaseOrderChangeCommand(
                expected_po_version=add_version,
                base_revision=add_revision,
                change_identity="CO-MIXED-ADD",
                reason="Add remaining vendor obligations",
                idempotency_key="request-mixed-add",
                changes=(
                    PurchaseOrderChangeOperation(
                        operation="add_line",
                        description="Partial line",
                        quantity=Decimal(6),
                        unit="each",
                        unit_cost=Decimal(2),
                    ),
                    PurchaseOrderChangeOperation(
                        operation="add_line",
                        description="Canceled line",
                        quantity=Decimal(8),
                        unit="each",
                        unit_cost=Decimal(3),
                    ),
                ),
            ),
        )
    async with factory() as session:
        await service.decide_change(
            session,
            context=approver,
            po_id=po_id,
            change_id=added.id,
            action="approve",
            payload=DecidePurchaseOrderChangeCommand(
                expected_po_version=add_version,
                expected_base_revision=add_revision,
                idempotency_key="approve-mixed-add",
            ),
        )
    async with factory() as session:
        order = await service.get_order(session, context=preparer, po_id=po_id)
        partial_line = next(line for line in order.lines if line.quantity == 6)
        canceled_line = next(line for line in order.lines if line.quantity == 8)
        cancel_version = order.version
        cancel_revision = order.effective_revision
    async with factory() as session:
        canceled = await service.request_change(
            session,
            context=preparer,
            po_id=po_id,
            payload=RequestPurchaseOrderChangeCommand(
                expected_po_version=cancel_version,
                base_revision=cancel_revision,
                change_identity="CO-MIXED-CANCEL",
                reason="Vendor cannot supply final line",
                idempotency_key="request-mixed-cancel",
                changes=(
                    PurchaseOrderChangeOperation(
                        operation="cancel_line", line_id=canceled_line.id
                    ),
                ),
            ),
        )
    async with factory() as session:
        await service.decide_change(
            session,
            context=approver,
            po_id=po_id,
            change_id=canceled.id,
            action="approve",
            payload=DecidePurchaseOrderChangeCommand(
                expected_po_version=cancel_version,
                expected_base_revision=cancel_revision,
                idempotency_key="approve-mixed-cancel",
            ),
        )
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        receipt_version = order.version
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                receipt_version, partial_line.id, "2", "mixed-partial-receipt"
            ),
        )
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        terminal_version = order.version
        terminal_revision = order.effective_revision
        before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (
                    InventoryItem,
                    StockMovement,
                    MaterialIssue,
                    AccountingVendor,
                    VendorBill,
                    Journal,
                    PaymentIntent,
                    Refund,
                    CompanyFinancePolicyVersion,
                )
            ]
        )
    async with factory() as session:
        result = await service.terminal_disposition(
            session,
            context=approver,
            po_id=po_id,
            action="cancel",
            payload=disposition(
                terminal_version,
                terminal_revision,
                "mixed-terminal-cancel",
                "Close mixed vendor obligations",
            ),
        )
        assert result.disposition == "remainder_canceled"
        outcomes = {
            int(item["line_number"]): (
                Decimal(str(item["effective_ordered_quantity"])),
                Decimal(str(item["accepted_received_quantity"])),
                Decimal(str(item["canceled_remainder_quantity"])),
            )
            for item in result.quantity_evidence
        }
        assert sorted(outcomes.values()) == sorted(
            [
                (Decimal(10), Decimal(10), Decimal(0)),
                (Decimal(6), Decimal(2), Decimal(4)),
                (Decimal(8), Decimal(0), Decimal(8)),
            ]
        )
        assert all(
            ordered == accepted + canceled
            for ordered, accepted, canceled in outcomes.values()
        )
        after = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (
                    InventoryItem,
                    StockMovement,
                    MaterialIssue,
                    AccountingVendor,
                    VendorBill,
                    Journal,
                    PaymentIntent,
                    Refund,
                    CompanyFinancePolicyVersion,
                )
            ]
        )
        assert after == before


@pytest.mark.asyncio
async def test_disposition_blocks_open_discrepancy_and_stale_or_racing_action(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version,
                line_id,
                "2",
                "disputed-receipt",
                rejected="1",
                category="damaged_item",
            ),
        )
    async with factory() as session:
        item = await service.get_order(session, context=approver, po_id=po_id)
    async with factory() as session:
        with pytest.raises(PurchasingValidation, match="discrepancies"):
            await service.terminal_disposition(
                session,
                context=approver,
                po_id=po_id,
                action="cancel",
                payload=disposition(
                    item.version, 1, "blocked-discrepancy", "Cannot fulfill remainder"
                ),
            )
    async with factory() as session:
        with pytest.raises(PurchasingConflict, match="stale"):
            await service.terminal_disposition(
                session,
                context=approver,
                po_id=po_id,
                action="cancel",
                payload=disposition(version, 1, "stale-cancel", "Stale cancellation"),
            )
    async with factory() as session:
        evidence_count = await session.scalar(
            select(func.count())
            .select_from(PurchaseOrderDispositionEvidence)
            .where(PurchaseOrderDispositionEvidence.purchase_order_id == po_id)
        )
        assert evidence_count == 0


@pytest.mark.asyncio
async def test_vendor_performance_evidence_is_deterministic_and_missing_is_explicit(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, _, _ = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
    async with factory() as session:
        first = await service.vendor_performance_evidence(
            session, context=approver, vendor_id=order.vendor_id
        )
    async with factory() as session:
        replay = await service.vendor_performance_evidence(
            session, context=approver, vendor_id=order.vendor_id
        )

    assert first == replay
    assert first.evidence_digest == replay.evidence_digest
    assert first.summary.purchase_orders_observed == 1
    assert first.summary.ordered_quantity_observed == Decimal(10)
    promised = [
        item
        for item in first.evidence
        if item.evidence_type == "fulfillment.promised_date"
    ]
    assert promised and promised[0].availability == "unavailable"
    assert promised[0].value is None
    assert not any(
        token in item.evidence_type
        for item in first.evidence
        for token in ("score", "rating", "rank")
    )
    async with factory() as session:
        empty_window = await service.vendor_performance_evidence(
            session,
            context=approver,
            vendor_id=order.vendor_id,
            from_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    assert empty_window.evidence == ()
    assert empty_window.summary.purchase_orders_observed == 0


@pytest.mark.asyncio
async def test_vendor_receipt_and_discrepancy_evidence_preserves_observed_facts(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version,
                line_id,
                "4",
                "vendor-evidence-partial",
                rejected="1",
                category="damaged_item",
            ),
        )
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
    async with factory() as session:
        report = await service.vendor_performance_evidence(
            session, context=approver, vendor_id=order.vendor_id
        )

    assert report.summary.receipts_observed == 1
    assert report.summary.accepted_quantity_observed == Decimal(4)
    assert report.summary.rejected_quantity_observed == Decimal(1)
    assert report.summary.discrepancies_observed == 1
    discrepancy = next(
        item
        for item in report.evidence
        if item.evidence_type == "discrepancy.damaged_item"
    )
    assert discrepancy.value == "open"
    assert discrepancy.unit == "observed_fact_not_fault"
    assert any(
        item.evidence_type == "fulfillment.outstanding_quantity"
        and item.value == "6.000000"
        for item in report.evidence
    )
    assert any(
        item.evidence_type == "fulfillment.receipt_state"
        and item.value == "partially_received"
        for item in report.evidence
    )
    assert any(
        item.evidence_type == "lead_time.promised_to_receipt"
        and item.availability == "unavailable"
        for item in report.evidence
    )


@pytest.mark.asyncio
async def test_vendor_evidence_is_company_scoped(purchasing_fixture) -> None:
    factory, _, _, _, _, _, approver = purchasing_fixture
    service = PurchasingService()
    async with factory() as session:
        with pytest.raises(PurchasingNotFound):
            await service.vendor_performance_evidence(
                session, context=approver, vendor_id=uuid4()
            )


@pytest.mark.asyncio
async def test_partial_receipts_accumulate_finalize_and_replay(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        first_payload = receipt(version, line_id, "3", "receipt-first")
        first = await service.record_receipt(
            session, context=approver, po_id=po_id, payload=first_payload
        )
        replay = await service.record_receipt(
            session, context=approver, po_id=po_id, payload=first_payload
        )
        assert replay.id == first.id
        item = await service.get_order(session, context=approver, po_id=po_id)
        assert item.receiving_status == "partially_received"
        assert item.lines[0].cumulative_accepted_quantity == Decimal(3)
        assert item.lines[0].outstanding_quantity == Decimal(7)
        await session.rollback()
        with pytest.raises(PurchasingConflict):
            await service.record_receipt(
                session,
                context=approver,
                po_id=po_id,
                payload=first_payload.model_copy(
                    update={"source_reference": "changed"}
                ),
            )
        second = await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(item.version, line_id, "4", "receipt-second"),
        )
        item = await service.get_order(session, context=approver, po_id=po_id)
        assert second.id != first.id and item.lines[0].outstanding_quantity == Decimal(
            3
        )
        await session.rollback()
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(item.version, line_id, "3", "receipt-final"),
        )
        item = await service.get_order(session, context=approver, po_id=po_id)
        assert item.receiving_status == "fully_received"
        assert len(item.receipts) == 3
        await session.rollback()
        with pytest.raises(PurchasingValidation):
            await service.record_receipt(
                session,
                context=approver,
                po_id=po_id,
                payload=receipt(item.version, line_id, "1", "receipt-over"),
            )


@pytest.mark.asyncio
async def test_discrepancy_is_durable_resolvable_and_has_no_financial_or_stock_effect(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(factory, branch, preparer, approver)
    async with factory() as session:
        before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (StockMovement, VendorBill, Journal)
            ]
        )
        await session.rollback()
        await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version,
                line_id,
                "2",
                "receipt-damaged",
                rejected="1",
                category="damaged_item",
            ),
        )
        item = await service.get_order(session, context=approver, po_id=po_id)
        assert item.receiving_status == "discrepancy_outstanding"
        discrepancy = item.discrepancies[0]
        assert discrepancy.status == "open"
        await session.rollback()
        resolved = await service.resolve_discrepancy(
            session,
            context=approver,
            po_id=po_id,
            discrepancy_id=discrepancy.id,
            payload=ResolveDiscrepancyCommand(
                expected_po_version=item.version,
                expected_discrepancy_version=1,
                resolution="resolved_rejected",
                note="Return damaged unit",
                idempotency_key="resolve-damaged",
            ),
        )
        assert (
            resolved.status == "resolved_rejected"
            and resolved.resolved_by_user_id == approver.user.id
        )
        after = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (StockMovement, VendorBill, Journal)
            ]
        )
        assert after == before
        assert (
            await session.scalar(
                select(func.count()).select_from(PurchaseOrderDiscrepancy)
            )
            >= 1
        )
        events = tuple(
            (
                await session.scalars(
                    select(BusinessEvent).where(
                        BusinessEvent.entity_id.in_(
                            (item.receipts[0].id, discrepancy.id)
                        )
                    )
                )
            ).all()
        )
        assert {event.event_type for event in events} >= {
            "purchasing.purchase_order.receipt_recorded",
            "purchasing.purchase_order.discrepancy_opened",
            "purchasing.purchase_order.discrepancy_resolved",
        }


def return_command(
    version: int,
    receipt_id,
    receipt_line_id,
    quantity: str,
    key: str,
    *,
    authorization_required: bool = True,
) -> CreatePurchaseReturnCommand:
    return CreatePurchaseReturnCommand(
        expected_po_version=version,
        return_identity=f"return-{key}",
        receipt_id=receipt_id,
        receipt_line_id=receipt_line_id,
        quantity=Decimal(quantity),
        reason="defective",
        authorization_required=authorization_required,
        effective_date=datetime.now(timezone.utc).date(),
        idempotency_key=key,
    )


def return_transition(
    po_version: int, return_version: int, key: str, *, reference: str | None = None
) -> PurchaseReturnTransitionCommand:
    return PurchaseReturnTransitionCommand(
        expected_po_version=po_version,
        expected_return_version=return_version,
        vendor_authorization_reference=reference,
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_purchase_return_quantity_replay_and_non_financial_boundary(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(
        factory, branch, preparer, approver, quantity="5"
    )
    async with factory() as session:
        receipt_record = await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(
                version,
                line_id,
                "3",
                "return-source",
                rejected="2",
                category="damaged_item",
            ),
        )
        item = await service.get_order(session, context=approver, po_id=po_id)
        receipt_line_id = (
            await service.repository.receipt_lines(
                session, item.company_id, receipt_record.id
            )
        )[0].id
        before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (StockMovement, VendorBill, Journal)
            ]
        )
        po_version, receipt_id = item.version, receipt_record.id
        await session.rollback()
        payload = return_command(
            po_version,
            receipt_id,
            receipt_line_id,
            "2",
            "return-create",
        )
        created = await service.create_purchase_return(
            session, context=approver, po_id=po_id, payload=payload
        )
        replay = await service.create_purchase_return(
            session, context=approver, po_id=po_id, payload=payload
        )
        assert replay.id == created.id
        with pytest.raises(PurchasingConflict):
            await service.create_purchase_return(
                session,
                context=approver,
                po_id=po_id,
                payload=payload.model_copy(update={"quantity": Decimal(1)}),
            )
        current = await service.get_order(session, context=approver, po_id=po_id)
        assert current.returns[0].remaining_returnable_quantity == Decimal(1)
        current_version = current.version
        await session.rollback()
        with pytest.raises(PurchasingValidation):
            await service.create_purchase_return(
                session,
                context=approver,
                po_id=po_id,
                payload=return_command(
                    current_version,
                    receipt_id,
                    receipt_line_id,
                    "2",
                    "return-over",
                ),
            )
        after = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (StockMovement, VendorBill, Journal)
            ]
        )
        assert after == before
    async with factory() as session:
        report = await service.vendor_performance_evidence(
            session, context=approver, vendor_id=current.vendor_id
        )
    return_fact = next(
        item for item in report.evidence if item.evidence_type == "return.lifecycle"
    )
    assert return_fact.value == "requested"
    assert return_fact.unit == "operational_fact_not_fault"
    assert report.summary.returns_observed == 1


@pytest.mark.asyncio
async def test_purchase_return_authorization_lifecycle_cancel_and_events(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(
        factory, branch, preparer, approver, quantity="2"
    )
    async with factory() as session:
        receipt_record = await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(version, line_id, "2", "return-lifecycle-source"),
        )
        order = await service.get_order(session, context=approver, po_id=po_id)
        receipt_line_id = (
            await service.repository.receipt_lines(
                session, order.company_id, receipt_record.id
            )
        )[0].id
        po_version, receipt_id = order.version, receipt_record.id
        await session.rollback()
        record = await service.create_purchase_return(
            session,
            context=approver,
            po_id=po_id,
            payload=return_command(
                po_version,
                receipt_id,
                receipt_line_id,
                "1",
                "return-lifecycle",
            ),
        )
        po_version += 1
        record = await service.transition_purchase_return(
            session,
            context=approver,
            po_id=po_id,
            return_id=record.id,
            action="request_authorization",
            payload=return_transition(
                po_version, record.version, "return-auth-request"
            ),
        )
        po_version += 1
        return_id, return_version = record.id, record.version
        with pytest.raises(PurchasingValidation):
            await service.transition_purchase_return(
                session,
                context=approver,
                po_id=po_id,
                return_id=return_id,
                action="authorize",
                payload=return_transition(
                    po_version, return_version, "return-auth-missing"
                ),
            )
        record = await service.transition_purchase_return(
            session,
            context=approver,
            po_id=po_id,
            return_id=return_id,
            action="authorize",
            payload=return_transition(
                po_version, return_version, "return-authorize", reference="RMA-42"
            ),
        )
        po_version += 1
        for action in ("mark_ready", "mark_returned", "vendor_received", "close"):
            record = await service.transition_purchase_return(
                session,
                context=approver,
                po_id=po_id,
                return_id=record.id,
                action=action,
                payload=return_transition(
                    po_version, record.version, f"return-{action}"
                ),
            )
            po_version += 1
        assert (
            record.status == "closed"
            and record.vendor_authorization_reference == "RMA-42"
        )
        events = set(
            (
                await session.scalars(
                    select(BusinessEvent.event_type).where(
                        BusinessEvent.entity_id == record.id
                    )
                )
            ).all()
        )
        assert {
            "purchasing.purchase_return.created",
            "purchasing.purchase_return.authorized",
            "purchasing.purchase_return.returned",
            "purchasing.purchase_return.closed",
        }.issubset(events)


@pytest.mark.asyncio
async def test_returned_receiving_history_still_blocks_price_change(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(
        factory, branch, preparer, approver, quantity="2"
    )
    async with factory() as session:
        receipt_record = await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(version, line_id, "2", "PRICE-RETURN-SOURCE"),
        )
        receipt_id = receipt_record.id
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        receipt_line_id = (
            await service.repository.receipt_lines(
                session, order.company_id, receipt_id
            )
        )[0].id
        current_version = order.version
    async with factory() as session:
        returned = await service.create_purchase_return(
            session,
            context=approver,
            po_id=po_id,
            payload=return_command(
                current_version,
                receipt_id,
                receipt_line_id,
                "2",
                "PRICE-FULL-RETURN",
                authorization_required=False,
            ),
        )
        assert returned.quantity == Decimal(2)
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        current_version = order.version
    async with factory() as session:
        requested = await service.request_change(
            session,
            context=preparer,
            po_id=po_id,
            payload=price_change(current_version, line_id, "AFTER-FULL-RETURN"),
        )
        change_id = requested.id
    async with factory() as session:
        with pytest.raises(
            PurchasingValidation, match="POST_RECEIPT_PRICE_CHANGE_POLICY_REQUIRED"
        ):
            await service.decide_change(
                session,
                context=approver,
                po_id=po_id,
                change_id=change_id,
                action="approve",
                payload=DecidePurchaseOrderChangeCommand(
                    expected_po_version=current_version,
                    expected_base_revision=1,
                    idempotency_key="approve-after-full-return",
                ),
            )
    async with factory() as session:
        order = await service.get_order(session, context=approver, po_id=po_id)
        assert order.effective_revision == 1
        assert order.lines[0].unit_cost == Decimal("4.0000")


@pytest.mark.asyncio
async def test_concurrent_purchase_returns_cannot_exceed_accepted_quantity(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(
        factory, branch, preparer, approver, quantity="1"
    )
    async with factory() as session:
        receipt_record = await service.record_receipt(
            session,
            context=approver,
            po_id=po_id,
            payload=receipt(version, line_id, "1", "return-race-source"),
        )
        order = await service.get_order(session, context=approver, po_id=po_id)
        receipt_line_id = (
            await service.repository.receipt_lines(
                session, order.company_id, receipt_record.id
            )
        )[0].id
        receipt_id, po_version = (
            receipt_record.id,
            order.version,
        )

    async def attempt(key: str):
        async with factory() as session:
            return await service.create_purchase_return(
                session,
                context=approver,
                po_id=po_id,
                payload=return_command(
                    po_version, receipt_id, receipt_line_id, "1", key
                ),
            )

    results = await asyncio.gather(
        attempt("return-race-a"), attempt("return-race-b"), return_exceptions=True
    )
    assert sum(isinstance(result, PurchaseReturn) for result in results) == 1
    assert (
        sum(
            isinstance(result, (PurchasingConflict, PurchasingValidation))
            for result in results
        )
        == 1
    )


@pytest.mark.asyncio
async def test_concurrent_receiving_serializes_without_double_count(
    purchasing_fixture,
) -> None:
    factory, _, _, branch, _, preparer, approver = purchasing_fixture
    service = PurchasingService()
    po_id, line_id, version = await issued_order(
        factory, branch, preparer, approver, quantity="5"
    )

    async def attempt(key: str):
        async with factory() as session:
            return await service.record_receipt(
                session,
                context=approver,
                po_id=po_id,
                payload=receipt(version, line_id, "4", key),
            )

    results = await asyncio.gather(
        attempt("race-one"), attempt("race-two"), return_exceptions=True
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert any(isinstance(result, PurchasingConflict) for result in results)
    async with factory() as session:
        item = await service.get_order(session, context=approver, po_id=po_id)
        assert item.lines[0].cumulative_accepted_quantity == Decimal(4)
