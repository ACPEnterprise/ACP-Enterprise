import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.customer_migration.models import CustomerMigrationRun, CustomerSourceIdentity
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
    RecordManualPayment,
)
from app.invoicing.errors import InvoiceConflict, InvoiceNotFound
from app.invoicing.models import (
    AccountingPostingReceipt,
    ARLedgerEntry,
    Invoice,
    InvoiceIdempotency,
    InvoiceLine,
    ManualPaymentReceipt,
    PaymentReceiptEvidence,
)
from app.invoicing.service import InvoiceService
from app.jobs.models import Job, JobAppointmentLink
from app.operational_migration import (
    models as operational_migration_models,  # noqa: F401
)
from app.payments.models import PaymentTermPolicy
from app.payments.money_authority import MoneyAuthorityService
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.scheduling.models import Appointment
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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


@pytest.mark.parametrize(
    ("term_code", "net_days", "customer_specific", "expected_state"),
    [
        ("COD", None, False, "QUALIFYING"),
        ("DUE_ON_COMPLETION", None, True, "QUALIFYING"),
        ("DUE_ON_RECEIPT", None, True, "NOT_DUE_TODAY"),
        ("NET", 15, True, "NOT_DUE_TODAY"),
        ("NET", 30, True, "NOT_DUE_TODAY"),
        (None, None, False, "INCOMPLETE"),
    ],
)
@pytest.mark.asyncio
async def test_scheduled_cod_uses_exact_terms_and_accepted_estimate_value(
    invoice_fixture, term_code, net_days, customer_specific, expected_state
):
    factory, company, branch, actor, customer, estimate, spec = invoice_fixture
    local_today = datetime.now().astimezone().date()
    start = datetime.combine(
        local_today, datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(hours=16)
    appointment = Appointment(
        company_id=company.id,
        branch_id=branch.id,
        appointment_number=f"APT-{uuid4().int % 1000000:06d}",
        customer_id=customer.id,
        service_location_id=estimate.service_location_id,
        status="scheduled",
        arrival_window_start_at=start,
        arrival_window_end_at=start + timedelta(hours=2),
        expected_duration_minutes=120,
        scheduling_timezone="America/New_York",
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    async with factory() as session, session.begin():
        session.add(appointment)
        await session.flush()
        session.add(
            JobAppointmentLink(
                company_id=company.id,
                branch_id=branch.id,
                job_id=spec.job_id,
                appointment_id=appointment.id,
                visit_sequence=1,
                linked_by_user_id=actor.id,
            )
        )
        if term_code is not None:
            session.add(
                PaymentTermPolicy(
                    company_id=company.id,
                    customer_id=customer.id if customer_specific else None,
                    term_code=term_code,
                    net_days=net_days,
                    effective_from=local_today,
                    version=1,
                    source_system="acp_native",
                    source_record_id=None,
                    evidence_digest="a" * 64,
                    idempotency_key=f"term-{uuid4()}",
                    request_digest="b" * 64,
                    approved=True,
                    approved_by_user_id=actor.id,
                    created_by_user_id=actor.id,
                )
            )
    async with factory() as session:
        result = await MoneyAuthorityService().projection(
            session,
            company_id=company.id,
            authorized_branch_ids=frozenset({branch.id}),
            period_start=local_today,
            period_end=local_today,
            as_of=local_today,
            branch_id=branch.id,
        )
    cod = result["cod_expected_today"]
    assert len(cod["items"]) == 1
    assert cod["items"][0]["state"] == expected_state
    if expected_state == "QUALIFYING":
        assert cod["amount"] == Decimal("250.00")
        assert (
            cod["items"][0]["estimate_revision_id"] == estimate.current_revision.id
        )
        assert result["expected_collections_today"]["amount"] == Decimal("250.00")
    elif expected_state == "NOT_DUE_TODAY":
        assert cod["amount"] == Decimal("0.00")
    else:
        assert cod["amount"] is None
        assert result["expected_collections_today"]["evidence_state"] == "INCOMPLETE"


@pytest.mark.asyncio
async def test_money_projection_due_today_uses_exact_remaining_invoice_balance(
    invoice_fixture,
):
    factory, company, branch, actor, customer, _, spec = invoice_fixture
    async with factory() as session:
        invoice = await InvoiceService().create_from_estimate(session, spec)
    invoice = await issue(factory, actor, invoice)
    payment = RecordManualPayment(
        company_id=company.id,
        branch_id=branch.id,
        invoice_id=invoice.id,
        expected_version=invoice.version,
        actor_user_id=actor.id,
        idempotency_key="money-projection-partial-payment-1",
        occurred_at=datetime.now(timezone.utc),
        amount=Decimal("25.00"),
        payment_method="check",
        reference="CHECK 1001",
    )
    async with factory() as session:
        invoice, _ = await InvoiceService().record_manual_payment(session, payment)
    async with factory() as session:
        result = await MoneyAuthorityService().projection(
            session,
            company_id=company.id,
            authorized_branch_ids=frozenset({branch.id}),
            period_start=spec.due_date,
            period_end=spec.due_date,
            as_of=spec.due_date,
            branch_id=branch.id,
        )
    due = result["accounts_receivable_due_today"]
    assert due["invoice_count"] == 1
    assert due["amount"] == invoice.open_amount
    assert due["amount"] == invoice.total_amount - Decimal("25.00")
    assert due["items"][0]["invoice_id"] == invoice.id
    assert due["items"][0]["customer_id"] == customer.id
    assert result["expected_collections_today"]["amount"] == invoice.open_amount
    assert result["expected_collections_today"]["evidence_state"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_office_workspace_and_customer_balance_use_native_scoped_evidence(
    invoice_fixture,
):
    factory, company, branch, _, customer, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    as_of = spec.due_date
    async with factory() as session:
        rows = await service.workspace(
            session,
            company.id,
            frozenset({branch.id}),
            as_of=as_of,
            state="all",
            query=customer.display_name,
            limit=10,
        )
        balance = await service.customer_balance(
            session, company.id, frozenset({branch.id}), customer.id, as_of=as_of
        )
    assert len(rows) == 1
    assert rows[0]["id"] == invoice.id
    assert rows[0]["customer_display_name"] == customer.display_name
    assert rows[0]["job_number"].startswith("JOB-")
    assert rows[0]["aging_bucket"] == "paid"
    assert balance is not None
    assert balance["native_invoice_count"] == 1
    assert balance["invoice_total"] == invoice.total_amount
    assert balance["open_balance"] == Decimal("0.00")
    assert (
        balance["evidence_classifications"][0]["classification"]
        == "CURRENT_AUTHORITATIVE"
    )
    assert balance["evidence_classifications"][0]["source_system"] == "acp_native"
    assert balance["evidence_classifications"][1]["classification"] == "UNAVAILABLE"

    async with factory() as session:
        hidden = await service.workspace(
            session, company.id, frozenset({uuid4()}), as_of=as_of, state="all"
        )
    assert hidden == ()


@pytest.mark.asyncio
async def test_receivables_summary_separates_due_today_and_is_branch_scoped(
    invoice_fixture,
):
    factory, company, branch, actor, _, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    issued = await issue(factory, actor, invoice)
    async with factory() as session:
        summary = await service.receivables_summary(
            session,
            company.id,
            frozenset({branch.id}),
            as_of=spec.due_date,
            branch_id=branch.id,
        )
        concealed = await service.receivables_summary(
            session,
            company.id,
            frozenset({branch.id}),
            as_of=spec.due_date,
            branch_id=uuid4(),
        )
        due_today_rows = await service.workspace(
            session,
            company.id,
            frozenset({branch.id}),
            as_of=spec.due_date,
            state="open",
            aging_bucket_filter="due_today",
        )
        not_due_rows = await service.workspace(
            session,
            company.id,
            frozenset({branch.id}),
            as_of=spec.due_date,
            state="open",
            aging_bucket_filter="not_due",
        )
    buckets = {item["key"]: item for item in summary["buckets"]}
    assert summary["evidence_state"] == "AVAILABLE"
    assert summary["open_invoice_count"] == 1
    assert summary["total_open_amount"] == issued.open_amount
    assert buckets["due_today"]["invoice_count"] == 1
    assert buckets["due_today"]["amount"] == issued.open_amount
    assert buckets["not_due"]["amount"] == Decimal("0.00")
    assert [row["id"] for row in due_today_rows] == [issued.id]
    assert not_due_rows == ()
    assert concealed["evidence_state"] == "MEASURED_ZERO"
    assert concealed["open_invoice_count"] == 0


@pytest.mark.asyncio
async def test_invoice_candidates_remove_uuid_entry_and_exclude_invoiced_work(
    invoice_fixture,
):
    factory, company, branch, _, customer, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        candidates = await service.candidates(
            session, company.id, frozenset({branch.id})
        )
    assert len(candidates) == 1
    assert candidates[0]["job_id"] == spec.job_id
    assert candidates[0]["estimate_id"] == spec.estimate_id
    assert candidates[0]["customer_display_name"] == customer.display_name
    async with factory() as session:
        await service.create_from_estimate(session, spec)
    async with factory() as session:
        assert (
            await service.candidates(session, company.id, frozenset({branch.id})) == ()
        )
        assert await service.candidates(session, uuid4(), frozenset({branch.id})) == ()


@pytest.mark.asyncio
async def test_customer_balance_composes_only_explicit_customer_source_identity(
    invoice_fixture,
):
    factory, company, branch, actor, customer, _, spec = invoice_fixture
    run = CustomerMigrationRun(
        company_id=company.id,
        branch_id=branch.id,
        initiated_by_user_id=actor.id,
        source_system="housecall_pro",
        source_sha256="a" * 64,
        mode="import",
        status="completed",
        source_count=1,
        accepted_count=1,
        rejected_count=0,
        duplicate_count=0,
        unresolved_count=0,
        completed_at=datetime.now(timezone.utc),
    )
    async with factory() as session:
        session.add(run)
        await session.flush()
        session.add(
            CustomerSourceIdentity(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                source_system="housecall_pro",
                source_customer_id="hcp-customer-1",
                first_run_id=run.id,
            )
        )
        await session.commit()
    async with factory() as session:
        balance = await InvoiceService().customer_balance(
            session,
            company.id,
            frozenset({branch.id}),
            customer.id,
            as_of=spec.due_date,
        )
        foreign = await InvoiceService().customer_balance(
            session, uuid4(), frozenset({branch.id}), customer.id, as_of=spec.due_date
        )
    assert balance is not None
    source = balance["evidence_classifications"][1]
    assert source["company_id"] == str(company.id)
    assert source["customer_id"] == str(customer.id)
    assert source["classification"] == "HISTORICAL_SOURCE_EVIDENCE"
    assert source["source_record_identity"] == "hcp-customer-1"
    assert source["evidence_digest"] == "a" * 64
    assert foreign is None


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
        assert (
            await session.scalar(
                select(func.count(Invoice.id)).where(
                    Invoice.estimate_revision_id == invoice.estimate_revision_id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(InvoiceIdempotency.id)).where(
                    InvoiceIdempotency.invoice_id == invoice.id,
                    InvoiceIdempotency.operation == "create",
                )
            )
            == 2
        )
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
        replay = await service.record_posting_receipt(session, posting)
        assert replay.id == posted.id
    async with factory() as session:
        assert (
            await session.scalar(select(func.count(AccountingPostingReceipt.id))) == 1
        )
    async with factory() as session:
        with pytest.raises(InvoiceConflict):
            await service.record_posting_receipt(
                session, replace(posting, policy_version="contradictory-policy")
            )


@pytest.mark.asyncio
async def test_manual_check_payment_is_replay_safe_partial_and_not_settlement(
    invoice_fixture,
):
    factory, company, branch, actor, _, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    invoice = await issue(factory, actor, invoice)
    payment = RecordManualPayment(
        company_id=company.id,
        branch_id=branch.id,
        invoice_id=invoice.id,
        expected_version=invoice.version,
        actor_user_id=actor.id,
        idempotency_key="manual-check-payment-1",
        occurred_at=datetime.now(timezone.utc),
        amount=Decimal("25.00"),
        payment_method="check",
        reference="CHECK 1042",
    )
    async with factory() as session:
        applied, receipt = await service.record_manual_payment(session, payment)
    assert applied.status == "partially_paid"
    assert applied.open_amount == invoice.total_amount - Decimal("25.00")
    assert receipt.reference_label == "ending 1042"
    assert receipt.settlement_state == "not_asserted"
    assert receipt.accounting_state == "not_posted"
    async with factory() as session:
        replay_invoice, replay_receipt = await service.record_manual_payment(
            session, payment
        )
        assert replay_receipt.id == receipt.id
        assert replay_invoice.version == applied.version
        assert (
            await session.scalar(
                select(func.count(ManualPaymentReceipt.id)).where(
                    ManualPaymentReceipt.company_id == company.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(ARLedgerEntry.id)).where(
                    ARLedgerEntry.invoice_id == invoice.id,
                    ARLedgerEntry.entry_type == "payment_application",
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_manual_payment_duplicate_reference_and_tenant_scope_fail_closed(
    invoice_fixture,
):
    factory, company, branch, actor, _, _, spec = invoice_fixture
    service = InvoiceService()
    async with factory() as session:
        invoice = await service.create_from_estimate(session, spec)
    invoice = await issue(factory, actor, invoice)
    payment = RecordManualPayment(
        company_id=company.id,
        branch_id=branch.id,
        invoice_id=invoice.id,
        expected_version=invoice.version,
        actor_user_id=actor.id,
        idempotency_key="manual-check-duplicate-a",
        occurred_at=datetime.now(timezone.utc),
        amount=Decimal("10.00"),
        payment_method="check",
        reference="CHECK 2048",
    )
    async with factory() as session:
        applied, _ = await service.record_manual_payment(session, payment)
    async with factory() as session:
        with pytest.raises(InvoiceConflict, match="reference already"):
            await service.record_manual_payment(
                session,
                replace(
                    payment,
                    expected_version=applied.version,
                    idempotency_key="manual-check-duplicate-b",
                ),
            )
    async with factory() as session:
        with pytest.raises(InvoiceNotFound):
            await service.record_manual_payment(
                session,
                replace(
                    payment,
                    company_id=uuid4(),
                    idempotency_key="manual-check-foreign-company",
                ),
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
        assert (
            await session.scalar(
                select(func.count(PaymentReceiptEvidence.id)).where(
                    PaymentReceiptEvidence.company_id == company_id,
                    PaymentReceiptEvidence.receipt_id == fact.receipt_id,
                )
            )
            == 1
        )
    with pytest.raises(InvoiceConflict):
        await register(replace(fact, evidence_digest="d" * 64))
    with pytest.raises(InvoiceConflict):
        await register(replace(fact, verified_amount=Decimal("99.00")))
