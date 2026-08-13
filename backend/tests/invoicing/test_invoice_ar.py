from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

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
from app.invoicing.models import AccountingPostingReceipt, ARLedgerEntry, InvoiceLine
from app.invoicing.service import InvoiceService
from app.jobs.models import Job
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
    assert invoice.total_amount == estimate.current_revision.total_amount
    assert invoice.tax_amount == estimate.current_revision.tax_amount
    assert invoice.open_amount == Decimal("0.00")
    assert len(invoice.calculation_digest) == 64
    async with factory() as session:
        replay = await service.create_from_estimate(session, spec)
    assert replay.id == invoice.id
    issued = await issue(factory, actor, invoice)
    assert issued.open_amount == issued.total_amount
    async with factory() as session:
        assert await session.scalar(select(func.count(InvoiceLine.id))) == len(
            estimate.current_revision.lines
        )
        entries = tuple((await session.scalars(select(ARLedgerEntry))).all())
    assert len(entries) == 1
    assert entries[0].entry_type == "obligation"
    assert entries[0].amount == issued.total_amount


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
        assert (
            await session.scalar(select(func.count(AccountingPostingReceipt.id))) == 1
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
