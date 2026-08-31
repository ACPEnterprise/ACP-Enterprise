import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import Customer
from app.estimates.service import EstimateService
from app.events.models import BusinessEvent
from app.invoicing.contracts import (
    AmountMutation,
    CreateFromEstimate,
    InvoiceMutation,
    PaymentApplication,
    PaymentReceiptFact,
    PostingReceiptFact,
)
from app.invoicing.errors import InvoiceConflict, InvoiceNotFound
from app.invoicing.models import (
    AccountingPostingReceipt,
    ARLedgerEntry,
    Invoice,
    InvoiceIdempotency,
    InvoiceLine,
    PaymentReceiptEvidence,
)
from app.invoicing.service import InvoiceService
from app.jobs.models import Job
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from tests.estimates.test_estimate_conversion import (
    approved_estimate,
    conversion_spec,
)
from tests.estimates.test_estimate_foundation import (
    estimate_fixture as estimate_foundation_fixture,  # noqa: F401
)


@pytest_asyncio.fixture
async def invoice_fixture(estimate_foundation_fixture):  # noqa: F811
    factory, company, branch, actor, customer, location, snapshot = (
        estimate_foundation_fixture
    )
    estimate = await approved_estimate(
        factory, company, branch, actor, customer, location, snapshot
    )
    async with factory() as session:
        conversion = await EstimateService().convert_to_job(
            session, spec=conversion_spec(estimate, branch, actor)
        )
    now = datetime.now(timezone.utc)
    async with factory() as session:
        await session.execute(
            update(Job)
            .where(Job.id == conversion.job_id)
            .values(
                status="completed",
                activated_at=now,
                started_at=now,
                completed_at=now,
                completed_by_user_id=actor.id,
            )
        )
        await session.commit()
    spec = CreateFromEstimate(
        company_id=company.id,
        branch_id=branch.id,
        estimate_id=estimate.id,
        job_id=conversion.job_id,
        due_date=datetime.now(timezone.utc).date() + timedelta(days=30),
        terms="Net 30",
        actor_user_id=actor.id,
        idempotency_key="invoice-create-1",
    )
    return factory, company, branch, actor, customer, estimate, spec


async def issue(factory, actor, invoice):
    spec = InvoiceMutation(
        company_id=invoice.company_id,
        branch_id=invoice.branch_id,
        invoice_id=invoice.id,
        expected_version=invoice.version,
        actor_user_id=actor.id,
        idempotency_key="invoice-issue-1",
        occurred_at=datetime.now(timezone.utc),
    )
    async with factory() as session:
        return await InvoiceService().issue(session, spec)


@pytest.mark.asyncio
async def test_accepted_work_creates_and_issues_one_exact_receivable(invoice_fixture):
    factory, _, _, actor, _, estimate, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    assert invoice.status == "draft"
    assert invoice.identity_origin == "native"
    assert invoice.invoice_number.startswith("INV-")
    assert invoice.invoice_number[4:].isdigit()
    assert len(invoice.invoice_number[4:]) >= 6
    assert invoice.total_amount == estimate.current_revision.total_amount
    assert invoice.tax_amount == estimate.current_revision.tax_amount
    assert invoice.open_amount == Decimal("0.00")
    assert len(invoice.calculation_digest) == 64
    async with factory() as session:
        replay = await service.create_from_estimate(session, spec)
    assert replay.id == invoice.id
    async with factory() as session:
        alternate_key = await service.create_from_estimate(
            session, replace(spec, idempotency_key="invoice-create-alternate")
        )
        assert alternate_key.id == invoice.id
        assert await session.scalar(select(func.count(Invoice.id)).where(Invoice.estimate_revision_id == invoice.estimate_revision_id)) == 1
        assert await session.scalar(select(func.count(InvoiceIdempotency.id)).where(InvoiceIdempotency.invoice_id == invoice.id, InvoiceIdempotency.operation == "create")) == 2
    issued = await issue(factory, actor, invoice)
    assert issued.open_amount == issued.total_amount
    async with factory() as session:
        assert await session.scalar(
            select(func.count(InvoiceLine.id)).where(
                InvoiceLine.invoice_id == invoice.id
            )
        ) == len(estimate.current_revision.lines)
        entries = tuple(
            (
                await session.scalars(
                    select(ARLedgerEntry).where(
                        ARLedgerEntry.invoice_id == invoice.id
                    )
                )
            ).all()
        )
    assert len(entries) == 1
    assert entries[0].entry_type == "obligation"
    assert entries[0].amount == issued.total_amount
    async with factory() as session:
        idempotency_id = await session.scalar(
            select(InvoiceIdempotency.id).where(
                InvoiceIdempotency.invoice_id == invoice.id
            )
        )
    assert idempotency_id is not None
    async with factory() as session, session.begin():
        for model, evidence_id in (
            (ARLedgerEntry, entries[0].id),
            (InvoiceIdempotency, idempotency_id),
        ):
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        update(model)
                        .where(model.id == evidence_id)
                        .values(id=evidence_id)
                    )
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        delete(model).where(model.id == evidence_id)
                    )


@pytest.mark.asyncio
async def test_credit_writeoff_and_stale_or_contradictory_replay_fail_closed(
    invoice_fixture,
):
    factory, _, _, actor, _, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    invoice = await issue(factory, actor, invoice)
    mutation = AmountMutation(
        company_id=invoice.company_id,
        branch_id=invoice.branch_id,
        invoice_id=invoice.id,
        expected_version=invoice.version,
        actor_user_id=actor.id,
        idempotency_key="invoice-credit-1",
        occurred_at=datetime.now(timezone.utc),
        amount=Decimal("10.00"),
        reason_code="customer_accommodation",
    )
    async with factory() as session:
        credited = await service.credit(session, mutation)
    assert credited.open_amount == invoice.total_amount - Decimal("10.00")
    async with factory() as session:
        replay = await service.credit(session, mutation)
    assert replay.version == credited.version
    async with factory() as session:
        with pytest.raises(InvoiceConflict, match="conflicts"):
            await service.write_off(
                session,
                replace(mutation, expected_version=credited.version),
            )


@pytest.mark.asyncio
async def test_stale_invoice_mutation_fails_closed(invoice_fixture):
    factory, _, _, actor, _, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    invoice = await issue(factory, actor, invoice)
    async with factory() as session:
        with pytest.raises(InvoiceConflict, match="stale"):
            await service.credit(
                session,
                AmountMutation(
                    company_id=invoice.company_id,
                    branch_id=invoice.branch_id,
                    invoice_id=invoice.id,
                    expected_version=invoice.version - 1,
                    actor_user_id=actor.id,
                    idempotency_key="stale-invoice-credit",
                    occurred_at=datetime.now(timezone.utc),
                    amount=Decimal("10.00"),
                    reason_code="customer_accommodation",
                ),
            )


@pytest.mark.asyncio
async def test_verified_receipt_application_and_accounting_receipt_seams(
    invoice_fixture,
):
    factory, company, branch, actor, customer, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    invoice = await issue(factory, actor, invoice)
    receipt_id = uuid4()
    async with factory() as session:
        evidence = await service.register_payment_receipt(
            session,
            PaymentReceiptFact(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                receipt_id=receipt_id,
                currency=invoice.currency,
                verified_amount=Decimal("25.00"),
                occurred_at=datetime.now(timezone.utc),
                evidence_digest="a" * 64,
            ),
        )
    assert evidence.available_amount == Decimal("25.00")
    application = PaymentApplication(
        company_id=company.id,
        branch_id=branch.id,
        invoice_id=invoice.id,
        expected_version=invoice.version,
        actor_user_id=actor.id,
        idempotency_key="invoice-payment-1",
        occurred_at=datetime.now(timezone.utc),
        receipt_id=receipt_id,
        amount=Decimal("25.00"),
    )
    async with factory() as session:
        applied = await service.apply_payment(session, application)
    assert applied.status == "partially_paid"
    assert applied.open_amount == invoice.total_amount - Decimal("25.00")
    async with factory() as session:
        reversed_invoice = await service.reverse_payment_application(
            session,
            replace(
                application,
                expected_version=applied.version,
                idempotency_key="invoice-payment-reversal-1",
            ),
        )
    assert reversed_invoice.status == "issued"
    assert reversed_invoice.open_amount == invoice.total_amount
    async with factory() as session:
        source_event_id = await session.scalar(
            select(BusinessEvent.id)
            .where(
                BusinessEvent.company_id == company.id,
                BusinessEvent.entity_type == "invoice",
                BusinessEvent.entity_id == reversed_invoice.id,
                BusinessEvent.event_type == "invoice.issued",
            )
            .order_by(BusinessEvent.occurred_at.desc())
        )
    assert source_event_id is not None
    posting = PostingReceiptFact(
        company_id=company.id,
        branch_id=branch.id,
        invoice_id=reversed_invoice.id,
        source_event_id=source_event_id,
        journal_id=uuid4(),
        journal_version=1,
        policy_version="quickbooks-basis-v1",
        status="posted",
        effective_date=datetime.now(timezone.utc).date(),
        posted_at=datetime.now(timezone.utc),
    )
    async with factory() as session:
        posted = await service.record_posting_receipt(session, posting)
    assert posted.accounting_status == "posted"
    async with factory() as session:
        replay = await service.record_posting_receipt(session, posting)
        assert replay.id == posted.id
    async with factory() as session:
        receipt_id = await session.scalar(
            select(AccountingPostingReceipt.id).where(
                AccountingPostingReceipt.invoice_id == posted.id
            )
        )
        assert receipt_id is not None
    async with factory() as session, session.begin():
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(AccountingPostingReceipt)
                    .where(AccountingPostingReceipt.id == receipt_id)
                    .values(id=receipt_id)
                )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    delete(AccountingPostingReceipt).where(
                        AccountingPostingReceipt.id == receipt_id
                    )
                )
    async with factory() as session:
        with pytest.raises(InvoiceConflict):
            await service.record_posting_receipt(
                session, replace(posting, policy_version="contradictory-policy")
            )


@pytest.mark.asyncio
async def test_company_branch_and_source_linkage_are_closed(invoice_fixture):
    factory, _, _, _, _, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        with pytest.raises(InvoiceNotFound):
            await service.create_from_estimate(
                session,
                replace(spec, company_id=uuid4(), idempotency_key="wrong-company"),
            )
    async with factory() as session:
        with pytest.raises(InvoiceNotFound):
            await service.create_from_estimate(
                session,
                replace(spec, branch_id=uuid4(), idempotency_key="wrong-branch"),
            )


@pytest_asyncio.fixture
async def receipt_concurrency_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Invoice receipt concurrency",
            code=f"IRC{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"I{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add_all([company, branch])
        await session.flush()
        customer = Customer(
            company_id=company.id,
            customer_number=f"CUS-{uuid4().int % 1000000:06d}",
            status="active",
            customer_type="residential",
            display_name="Receipt Customer",
            preferred_contact_method="email",
            normalized_name="receipt customer",
        )
        session.add(customer)
        await session.flush()
        ids = company.id, branch.id, customer.id
    try:
        yield factory, ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_payment_receipt_registration_has_one_authority(
    receipt_concurrency_fixture,
) -> None:
    factory, (company_id, branch_id, customer_id) = receipt_concurrency_fixture
    service = InvoiceService()
    fact = PaymentReceiptFact(
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer_id,
        receipt_id=uuid4(),
        currency="USD",
        verified_amount=Decimal("37.25"),
        occurred_at=datetime.now(timezone.utc),
        evidence_digest="c" * 64,
    )

    async def register(value: PaymentReceiptFact):
        async with factory() as session:
            return await service.register_payment_receipt(session, value)

    first, replay = await asyncio.gather(register(fact), register(fact))
    assert first.id == replay.id
    async with factory() as session:
        assert await session.scalar(select(func.count(PaymentReceiptEvidence.id)).where(PaymentReceiptEvidence.company_id == company_id, PaymentReceiptEvidence.receipt_id == fact.receipt_id)) == 1
    with pytest.raises(InvoiceConflict):
        await register(replace(fact, evidence_digest="d" * 64))
    with pytest.raises(InvoiceConflict):
        await register(replace(fact, verified_amount=Decimal("99.00")))
