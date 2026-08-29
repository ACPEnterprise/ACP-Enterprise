import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounting.models import Account, ChartVersion, Journal
from app.accounts_payable.models import (
    AccountingVendor,
    APAccountMapping,
    APSubledgerEntry,
    BillLine,
    BillRevision,
    VendorBill,
    VendorCredit,
    VendorSourceMapping,
)
from app.core.config import settings
from app.events.models import BusinessEvent
from app.inventory.models import InventoryQuantity, StockMovement
from app.payments.models import PaymentIntent
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.procurement_matching.errors import ProcurementMatchingConflict
from app.procurement_matching.models import (
    ProcurementMatch,
    ProcurementMatchException,
)
from app.procurement_matching.schemas import (
    EvaluateMatchCommand,
    ResolveMatchExceptionCommand,
)
from app.procurement_matching.service import (
    ProcurementMatchingService,
    is_current_eligible_match,
)
from app.purchasing.models import (
    OperationalVendor,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    PurchaseReturn,
)


@pytest_asyncio.fixture
async def matching_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Three Way Match Test",
            code=f"TWM{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"M{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        evaluator = User(
            normalized_email=f"match-{uuid4().hex}@example.test",
            first_name="Match",
            last_name="Evaluator",
            display_name="Match Evaluator",
            status="active",
        )
        reviewer = User(
            normalized_email=f"review-{uuid4().hex}@example.test",
            first_name="Match",
            last_name="Reviewer",
            display_name="Match Reviewer",
            status="active",
        )
        session.add_all([company, branch, evaluator, reviewer])
        await session.flush()
        evaluator_membership = Membership(
            user_id=evaluator.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=True,
        )
        reviewer_membership = Membership(
            user_id=reviewer.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=True,
        )
        session.add_all([evaluator_membership, reviewer_membership])
        await session.flush()

    def context(user, membership):
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
            branch,
            context(evaluator, evaluator_membership),
            context(reviewer, reviewer_membership),
        )
    finally:
        await engine.dispose()


async def seed_evidence(
    factory,
    company,
    branch,
    actor,
    *,
    received=Decimal(10),
    billed=Decimal(10),
    billed_net=Decimal(100),
):
    async with factory() as session, session.begin():
        operational_vendor = OperationalVendor(
            company_id=company.id,
            code=f"OP-{uuid4().hex[:8]}",
            display_name="Operational Vendor",
            created_by_user_id=actor.user.id,
        )
        ap_vendor = AccountingVendor(
            company_id=company.id,
            code=f"AP-{uuid4().hex[:8]}",
            legal_name="Accounting Vendor LLC",
            display_name="Accounting Vendor",
            provenance="native",
            created_by_user_id=actor.user.id,
        )
        chart = ChartVersion(
            company_id=company.id,
            version=1,
            name="Match Chart",
            currency="USD",
            accounting_basis="accrual",
            source_checksum="a" * 64,
            effective_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            is_active=True,
            approved_by_user_id=actor.user.id,
        )
        session.add_all([operational_vendor, ap_vendor, chart])
        await session.flush()
        account = Account(
            company_id=company.id,
            chart_version_id=chart.id,
            code=f"5{uuid4().hex[:5]}",
            name="Inventory clearing evidence",
            classification="expense",
            normal_balance="debit",
            effective_from=date(2026, 1, 1),
        )
        order = PurchaseOrder(
            company_id=company.id,
            branch_id=branch.id,
            vendor_id=operational_vendor.id,
            po_number=f"PO-{uuid4().hex[:8]}",
            status="issued",
            currency="USD",
            prepared_by_user_id=actor.user.id,
            issued_by_user_id=actor.user.id,
            issued_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        )
        session.add_all([account, order])
        await session.flush()
        mapping = APAccountMapping(
            company_id=company.id,
            mapping_key=f"match-{uuid4()}",
            classification="expense",
            account_id=account.id,
            effective_from=date(2026, 1, 1),
            policy_version="synthetic-test-v1",
            approved_by_user_id=actor.user.id,
        )
        po_line = PurchaseOrderLine(
            company_id=company.id,
            purchase_order_id=order.id,
            line_number=1,
            description="Synthetic received material",
            quantity=Decimal(10),
            unit="each",
            unit_cost=Decimal(10),
            extended_cost=Decimal(100),
            created_by_user_id=actor.user.id,
        )
        bill = VendorBill(
            company_id=company.id,
            branch_id=branch.id,
            vendor_id=ap_vendor.id,
            bill_number=f"B-{uuid4().hex[:8]}",
            vendor_document_number=f"DOC-{uuid4().hex[:8]}",
            normalized_document_number=uuid4().hex.upper(),
            bill_date=date(2026, 8, 29),
            received_date=date(2026, 8, 29),
            due_date=date(2026, 9, 28),
            terms_snapshot="Net 30",
            currency="USD",
            total_amount=billed_net,
            open_amount=billed_net,
            source_system="synthetic-test",
            source_identity=str(uuid4()),
            source_digest="b" * 64,
            evidence_reference="synthetic://vendor-bill",
            prepared_by_user_id=actor.user.id,
        )
        vendor_mapping = VendorSourceMapping(
            company_id=company.id,
            vendor_id=ap_vendor.id,
            source_system="purchasing",
            source_company_id=str(company.id),
            source_vendor_id=str(operational_vendor.id),
            source_digest="c" * 64,
            mapped_by_user_id=actor.user.id,
        )
        session.add_all([mapping, po_line, bill, vendor_mapping])
        await session.flush()
        receipt = PurchaseOrderReceipt(
            company_id=company.id,
            branch_id=branch.id,
            purchase_order_id=order.id,
            vendor_id=operational_vendor.id,
            inventory_application_state="not_applicable",
            receiving_event_identity=f"receipt-{uuid4()}",
            status="recorded",
            receiver_user_id=actor.user.id,
            received_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
            effective_date=date(2026, 8, 29),
            payload_digest="d" * 64,
        )
        revision = BillRevision(
            company_id=company.id,
            bill_id=bill.id,
            revision=1,
            canonical_digest="e" * 64,
            created_by_user_id=actor.user.id,
        )
        session.add_all([receipt, revision])
        await session.flush()
        receipt_line = PurchaseOrderReceiptLine(
            company_id=company.id,
            receipt_id=receipt.id,
            purchase_order_line_id=po_line.id,
            ordered_quantity_snapshot=Decimal(10),
            accepted_quantity=received,
            rejected_quantity=Decimal(0),
            cumulative_accepted_quantity=received,
            outstanding_quantity=Decimal(10) - received,
            unit_snapshot="each",
            unit_cost_snapshot=Decimal(10),
            currency_snapshot="USD",
        )
        bill_line = BillLine(
            company_id=company.id,
            revision_id=revision.id,
            position=1,
            description="Synthetic received material",
            quantity=billed,
            unit="each",
            net_amount=billed_net,
            tax_amount=Decimal(0),
            mapping_id=mapping.id,
            branch_id=branch.id,
            purchasing_reference=str(po_line.id),
        )
        session.add_all([receipt_line, bill_line])
        await session.flush()
    return order, bill


async def seed_physical_return(factory, company, actor, order, quantity=Decimal(2)):
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    async with factory() as session, session.begin():
        receipt = await session.scalar(
            select(PurchaseOrderReceipt).where(
                PurchaseOrderReceipt.company_id == company.id,
                PurchaseOrderReceipt.purchase_order_id == order.id,
            )
        )
        assert receipt is not None
        line = await session.scalar(
            select(PurchaseOrderReceiptLine).where(
                PurchaseOrderReceiptLine.company_id == company.id,
                PurchaseOrderReceiptLine.receipt_id == receipt.id,
            )
        )
        assert line is not None
        po_line = await session.get(PurchaseOrderLine, line.purchase_order_line_id)
        assert po_line is not None
        returned = PurchaseReturn(
            company_id=company.id,
            branch_id=order.branch_id,
            purchase_order_id=order.id,
            vendor_id=order.vendor_id,
            receipt_id=receipt.id,
            receipt_line_id=line.id,
            purchase_order_line_id=po_line.id,
            return_identity=f"return-{uuid4()}",
            item_identity_snapshot=str(po_line.inventory_item_id or po_line.id),
            accepted_quantity_snapshot=line.accepted_quantity,
            quantity=quantity,
            reason="defective",
            reason_note="Synthetic return evidence",
            status="returned",
            authorization_status="received",
            requested_by_user_id=actor.user.id,
            requested_at=now,
            effective_date=now.date(),
            updated_by_user_id=actor.user.id,
            updated_at=now,
            authorization_at=now,
            returned_at=now,
        )
        session.add(returned)
        await session.flush()
        return returned


@pytest.mark.asyncio
async def test_exact_match_is_idempotent_current_and_has_zero_downstream_effects(
    matching_fixture,
):
    factory, company, _, evaluator, _ = matching_fixture
    order, bill = await seed_evidence(
        factory, company, evaluator.active_branch, evaluator
    )
    command = EvaluateMatchCommand(
        purchase_order_id=order.id,
        vendor_bill_id=bill.id,
        expected_purchase_order_version=order.version,
        expected_bill_version=bill.version,
        idempotency_key=f"match-{uuid4()}",
    )
    boundary_models = (
        InventoryQuantity,
        StockMovement,
        APSubledgerEntry,
        Journal,
        PaymentIntent,
    )
    service = ProcurementMatchingService()
    async with factory() as session:
        before = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in boundary_models
            ]
        )
    async with factory() as session:
        first = await service.evaluate(session, context=evaluator, payload=command)
        replay = await service.evaluate(session, context=evaluator, payload=command)
    async with factory() as session:
        after = tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in boundary_models
            ]
        )
        assert first.id == replay.id
        assert first.state == "matched"
        assert first.admission_state == "eligible"
        assert first.lines[0].net_accepted_quantity == Decimal(10)
        assert before == after
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProcurementMatch)
                .where(ProcurementMatch.company_id == company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.entity_id == first.id)
            )
            == 1
        )
        match = await session.get(ProcurementMatch, first.id)
        assert match is not None
        assert await is_current_eligible_match(session, match, bill)
    async with factory() as session, session.begin():
        current = await session.get(PurchaseOrder, order.id, with_for_update=True)
        assert current is not None
        current.version += 1
    async with factory() as session:
        match = await session.get(ProcurementMatch, first.id)
        current_bill = await session.get(VendorBill, bill.id)
        assert match is not None and current_bill is not None
        assert not await is_current_eligible_match(session, match, current_bill)


@pytest.mark.asyncio
async def test_return_and_vendor_credit_create_append_only_match_revisions(
    matching_fixture,
):
    factory, company, _, evaluator, _ = matching_fixture
    order, bill = await seed_evidence(
        factory, company, evaluator.active_branch, evaluator
    )
    service = ProcurementMatchingService()

    async def evaluate(key: str):
        async with factory() as session:
            return await service.evaluate(
                session,
                context=evaluator,
                payload=EvaluateMatchCommand(
                    purchase_order_id=order.id,
                    vendor_bill_id=bill.id,
                    expected_purchase_order_version=order.version,
                    expected_bill_version=bill.version,
                    idempotency_key=key,
                ),
            )

    initial_key = f"initial-{uuid4()}"
    initial = await evaluate(initial_key)
    returned = await seed_physical_return(factory, company, evaluator, order)
    async with factory() as session:
        stale = await session.get(ProcurementMatch, initial.id)
        current_bill = await session.get(VendorBill, bill.id)
        assert stale is not None and current_bill is not None
        assert not await is_current_eligible_match(session, stale, current_bill)

    pending = await evaluate(f"return-{uuid4()}")
    assert pending.state == "return_pending_credit"
    assert pending.admission_state == "review_required"
    assert pending.evaluation_sequence == 2
    assert pending.supersedes_match_id == initial.id

    async with factory() as session, session.begin():
        ap_vendor = await session.get(AccountingVendor, bill.vendor_id)
        mapping = await session.scalar(
            select(APAccountMapping).where(APAccountMapping.company_id == company.id)
        )
        assert ap_vendor is not None and mapping is not None
        session.add(
            VendorCredit(
                company_id=company.id,
                vendor_id=ap_vendor.id,
                credit_number=f"VC-{uuid4().hex[:8]}",
                credit_date=date(2026, 8, 30),
                currency="USD",
                amount=Decimal(20),
                available_amount=Decimal(20),
                reason="Returned defective material",
                mapping_id=mapping.id,
                source_system="purchasing_return",
                source_identity=str(returned.id),
                source_digest="f" * 64,
                created_by_user_id=evaluator.user.id,
            )
        )

    reviewed = await evaluate(f"credit-{uuid4()}")
    assert reviewed.state == "requires_review"
    assert reviewed.admission_state == "review_required"
    assert reviewed.evaluation_sequence == 3
    assert reviewed.supersedes_match_id == pending.id
    assert reviewed.lines[0].returned_quantity == Decimal(2)
    assert reviewed.exceptions[0].category == "return_pending_credit"
    historical_replay = await evaluate(initial_key)
    assert historical_replay.id == initial.id
    assert historical_replay.superseded_at is not None

    async with factory() as session:
        matches = tuple(
            (
                await session.scalars(
                    select(ProcurementMatch)
                    .where(ProcurementMatch.vendor_bill_id == bill.id)
                    .order_by(ProcurementMatch.evaluation_sequence)
                )
            ).all()
        )
        assert [row.evaluation_sequence for row in matches] == [1, 2, 3]
        assert matches[0].superseded_at is not None
        assert matches[1].superseded_at is not None
        assert matches[2].superseded_at is None


@pytest.mark.asyncio
async def test_variance_requires_independent_review_and_resolution_is_idempotent(
    matching_fixture,
):
    factory, company, _, evaluator, reviewer = matching_fixture
    order, bill = await seed_evidence(
        factory,
        company,
        evaluator.active_branch,
        evaluator,
        received=Decimal(4),
        billed=Decimal(5),
        billed_net=Decimal(55),
    )
    service = ProcurementMatchingService()
    command = EvaluateMatchCommand(
        purchase_order_id=order.id,
        vendor_bill_id=bill.id,
        expected_purchase_order_version=order.version,
        expected_bill_version=bill.version,
        idempotency_key=f"variance-{uuid4()}",
    )
    async with factory() as session:
        result = await service.evaluate(session, context=evaluator, payload=command)
        assert result.state == "overbilled"
        assert result.admission_state == "review_required"
        exception = result.exceptions[0]
        resolution = ResolveMatchExceptionCommand(
            expected_match_version=result.version,
            expected_exception_version=exception.version,
            resolution="accept_variance",
            note="Synthetic independent review evidence",
            idempotency_key=f"resolve-{uuid4()}",
        )
        with pytest.raises(Exception, match="cannot approve"):
            await service.resolve(
                session,
                context=evaluator,
                match_id=result.id,
                exception_id=exception.id,
                payload=resolution,
            )
        accepted = await service.resolve(
            session,
            context=reviewer,
            match_id=result.id,
            exception_id=exception.id,
            payload=resolution,
        )
        replay = await service.resolve(
            session,
            context=reviewer,
            match_id=result.id,
            exception_id=exception.id,
            payload=resolution,
        )
        assert accepted.id == replay.id
        assert accepted.admission_state == "eligible"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProcurementMatchException)
                .where(ProcurementMatchException.match_id == result.id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_concurrent_equivalent_evaluation_creates_one_authority(matching_fixture):
    factory, company, _, evaluator, _ = matching_fixture
    order, bill = await seed_evidence(
        factory, company, evaluator.active_branch, evaluator
    )
    service = ProcurementMatchingService()

    async def evaluate(key):
        async with factory() as session:
            return await service.evaluate(
                session,
                context=evaluator,
                payload=EvaluateMatchCommand(
                    purchase_order_id=order.id,
                    vendor_bill_id=bill.id,
                    expected_purchase_order_version=order.version,
                    expected_bill_version=bill.version,
                    idempotency_key=key,
                ),
            )

    first, second = await asyncio.gather(
        evaluate(f"concurrent-{uuid4()}"), evaluate(f"concurrent-{uuid4()}")
    )
    assert first.id == second.id
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProcurementMatch)
                .where(ProcurementMatch.vendor_bill_id == bill.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.entity_id == first.id)
            )
            == 1
        )
    async with factory() as session:
        with pytest.raises(ProcurementMatchingConflict):
            await service.evaluate(
                session,
                context=evaluator,
                payload=EvaluateMatchCommand(
                    purchase_order_id=uuid4(),
                    vendor_bill_id=bill.id,
                    expected_purchase_order_version=1,
                    expected_bill_version=1,
                    idempotency_key=f"contradictory-{uuid4()}",
                ),
            )


@pytest.mark.asyncio
async def test_vendor_performance_is_deterministic_evidence_not_a_vendor_score(
    matching_fixture,
):
    factory, company, branch, evaluator, _ = matching_fixture
    order, bill = await seed_evidence(
        factory,
        company,
        branch,
        evaluator,
        received=Decimal(4),
        billed=Decimal(4),
        billed_net=Decimal(40),
    )
    service = ProcurementMatchingService()
    async with factory() as session:
        await service.evaluate(
            session,
            context=evaluator,
            payload=EvaluateMatchCommand(
                purchase_order_id=order.id,
                vendor_bill_id=bill.id,
                expected_purchase_order_version=order.version,
                expected_bill_version=bill.version,
                idempotency_key=f"performance-{uuid4()}",
            ),
        )
        evaluated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
        first = await service.vendor_performance(
            session,
            context=evaluator,
            evaluated_at=evaluated_at,
            branch_id=branch.id,
        )
        replay = await service.vendor_performance(
            session,
            context=evaluator,
            evaluated_at=evaluated_at,
            branch_id=branch.id,
        )
        assert first == replay
        assert first.evidence_digest == replay.evidence_digest
        assert len(first.items) == 1
        item = first.items[0]
        assert item.ordered_quantity == Decimal(10)
        assert item.accepted_received_quantity == Decimal(4)
        assert item.net_accepted_quantity == Decimal(4)
        assert item.fulfillment_ratio == Decimal("0.4000")
        assert item.completed_lead_time_samples == 1
        assert item.average_lead_time_days == Decimal("1.00")
        assert not hasattr(item, "score")
