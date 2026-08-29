import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounting.models import Journal
from app.accounts_payable.models import AccountingVendor, VendorBill
from app.core.config import settings
from app.events.models import BusinessEvent
from app.inventory.models import StockMovement
from app.main import app
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
    PurchaseOrderDiscrepancy,
    PurchaseOrderIssuanceEvidence,
    PurchaseOrderRevision,
    PurchaseReturn,
)
from app.purchasing.schemas import (
    CreatePurchaseReturnCommand,
    DecidePurchaseOrderChangeCommand,
    PurchaseOrderChangeOperation,
    PurchaseOrderCreate,
    PurchaseOrderLineWrite,
    PurchaseReturnTransitionCommand,
    ReceiptLineCommand,
    RecordReceiptCommand,
    RequestPurchaseOrderChangeCommand,
    ResolveDiscrepancyCommand,
    TransitionCommand,
    VendorCreate,
    VendorUpdate,
)
from app.purchasing.service import PurchasingService


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
    async with factory() as session:
        first = await service.create_vendor(session, context=preparer, payload=payload)
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
async def test_branch_isolation_cancel_and_manual_nonreceipt_close(
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
        cancelled = await service.transition(
            session,
            context=approver,
            po_id=cancelled.id,
            target="cancel",
            payload=command(
                cancelled.version, "po-cancel-action", "No longer required"
            ),
        )
        assert cancelled.status == "cancelled"
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
        order = await service.transition(
            session,
            context=approver,
            po_id=order.id,
            target="close",
            payload=command(
                order.version, "po-close-action", "Owner-authorized non-receipt closure"
            ),
        )
        assert order.status == "closed" and "non-receipt" in (
            order.lifecycle_reason or ""
        )


@pytest.mark.asyncio
async def test_purchasing_api_requires_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/purchasing")
    assert response.status_code in {401, 403}


async def issued_order(factory, branch, preparer, approver, *, quantity: str = "10"):
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


def receipt(
    version: int,
    line_id,
    accepted: str,
    key: str,
    *,
    rejected: str = "0",
    category: str | None = None,
):
    return RecordReceiptCommand(
        expected_po_version=version,
        receiving_event_identity=f"event-{key}",
        received_at=datetime.now(timezone.utc),
        effective_date=datetime.now(timezone.utc).date(),
        idempotency_key=key,
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
