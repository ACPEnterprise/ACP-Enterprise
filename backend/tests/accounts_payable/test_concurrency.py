import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounts_payable.errors import APConflict, APNotFound
from app.accounts_payable.models import (
    AccountingVendor,
    APSubledgerEntry,
    Disbursement,
    DisbursementApplication,
    VendorBill,
)
from app.accounts_payable.service import AccountsPayableService
from app.core.config import settings
from app.customers import models as customer_models  # noqa: F401
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users.models import User
from app.scheduling import models as scheduling_models  # noqa: F401


@pytest_asyncio.fixture
async def ap_application_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="AP concurrency",
            code=f"AP{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"B{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        user = User(
            normalized_email=f"ap-{uuid4().hex}@example.test",
            first_name="AP",
            last_name="Actor",
            display_name="AP Actor",
            status="active",
        )
        session.add_all([company, branch, user])
        await session.flush()
        vendor = AccountingVendor(
            company_id=company.id,
            code=f"V{uuid4().hex[:8]}",
            legal_name="Synthetic Vendor",
            display_name="Synthetic Vendor",
            provenance="qualification",
            created_by_user_id=user.id,
        )
        session.add(vendor)
        await session.flush()
        bill = VendorBill(
            company_id=company.id,
            branch_id=branch.id,
            vendor_id=vendor.id,
            bill_number=f"BILL-{uuid4().hex[:8]}",
            vendor_document_number=f"DOC-{uuid4().hex[:8]}",
            normalized_document_number=uuid4().hex.upper(),
            bill_date=date(2026, 8, 30),
            received_date=date(2026, 8, 30),
            due_date=date(2026, 9, 30),
            terms_snapshot="Net 30",
            currency="USD",
            status="approved",
            total_amount=Decimal("100.00"),
            open_amount=Decimal("100.00"),
            source_system="qualification",
            source_identity=f"bill-{uuid4()}",
            source_digest="a" * 64,
            evidence_reference="restricted://qualification/bill",
            prepared_by_user_id=user.id,
            approved_by_user_id=uuid4(),
        )
        disbursement = Disbursement(
            company_id=company.id,
            branch_id=branch.id,
            vendor_id=vendor.id,
            amount=Decimal("100.00"),
            available_amount=Decimal("100.00"),
            currency="USD",
            effective_date=date(2026, 8, 30),
            method_category="synthetic",
            external_reference=f"EXT-{uuid4()}",
            source_system="qualification",
            source_identity=f"payment-{uuid4()}",
            evidence_digest="b" * 64,
            recorder_user_id=user.id,
            approver_user_id=uuid4(),
        )
        session.add_all([bill, disbursement])
        await session.flush()
        ids = company.id, branch.id, bill.id, disbursement.id, user.id
    try:
        yield factory, ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_disbursement_replay_has_one_application_and_conserves_amounts(
    ap_application_fixture,
) -> None:
    factory, (company_id, branch_id, bill_id, disbursement_id, actor_id) = ap_application_fixture
    service = AccountsPayableService()
    key = f"apply-{uuid4()}"

    async def apply():
        async with factory() as session:
            return await service.apply_disbursement(
                session,
                company_id,
                disbursement_id,
                bill_id,
                actor_id,
                Decimal("60.00"),
                key,
                frozenset({branch_id}),
            )

    first, replay = await asyncio.gather(apply(), apply())
    assert first.id == replay.id
    async with factory() as session:
        bill = await session.get(VendorBill, bill_id)
        disbursement = await session.get(Disbursement, disbursement_id)
        assert bill is not None and bill.open_amount == Decimal("40.00")
        assert disbursement is not None and disbursement.available_amount == Decimal("40.00")
        assert await session.scalar(select(func.count(DisbursementApplication.id)).where(DisbursementApplication.company_id == company_id, DisbursementApplication.idempotency_key == key)) == 1
        assert await session.scalar(select(func.count(APSubledgerEntry.id)).where(APSubledgerEntry.company_id == company_id, APSubledgerEntry.source_id == first.id)) == 1

    async with factory() as session:
        with pytest.raises(APConflict):
            await service.apply_disbursement(
                session,
                company_id,
                disbursement_id,
                bill_id,
                actor_id,
                Decimal("40.00"),
                key,
                frozenset({branch_id}),
            )

    async with factory() as session:
        with pytest.raises(APNotFound):
            await service.apply_disbursement(
                session,
                company_id,
                disbursement_id,
                bill_id,
                actor_id,
                Decimal("60.00"),
                key,
                frozenset({uuid4()}),
            )
