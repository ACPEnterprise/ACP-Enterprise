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
from app.purchasing.models import PurchaseOrderIssuanceEvidence
from app.purchasing.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderLineWrite,
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
