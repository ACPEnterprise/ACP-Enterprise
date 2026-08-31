import asyncio
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import Customer
from app.events.models import BusinessEvent
from app.invoicing.errors import InvoiceError
from app.payments.contracts import (
    ApplyReceipt,
    CreateDeposit,
    CreateIntent,
    PostingReceiptFact,
    ProviderRequest,
    RecordDispute,
    RecordSettlement,
    RequestRefund,
    VerifiedWebhook,
)
from app.payments.errors import PaymentConflict, PaymentNotFound, PaymentValidation
from app.payments.models import (
    Deposit,
    DepositReceipt,
    PaymentIntent,
    PaymentReceipt,
    ReceiptEvent,
    ReconciliationException,
    Refund,
)
from app.payments.provider import DeterministicFakeProvider
from app.payments.router import _error
from app.payments.service import PaymentService
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users.models import User
from app.scheduling.models import Appointment  # noqa: F401


class CountingFakeProvider(DeterministicFakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.collect_calls = 0
        self.collect_keys: list[str] = []
        self.refund_calls = 0
        self.refund_keys: list[str] = []

    async def collect(self, request: ProviderRequest):
        self.collect_calls += 1
        self.collect_keys.append(request.provider_idempotency_key)
        return await super().collect(request)

    async def refund(self, request: ProviderRequest):
        self.refund_calls += 1
        self.refund_keys.append(request.provider_idempotency_key)
        return await super().refund(request)


@pytest.mark.parametrize(
    ("error", "status_code", "code", "recovery"),
    [
        (PaymentNotFound("protected identifier"), 404, "not_found", "TERMINAL_FAILURE"),
        (
            PaymentConflict("downstream SQL or invoice detail"),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
        (
            PaymentValidation("protected provider payload"),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
    ],
)
def test_payment_failures_use_safe_non_reflective_recovery_contract(
    error, status_code: int, code: str, recovery: str
) -> None:
    translated = _error(error)
    assert translated.status_code == status_code
    assert translated.detail["code"] == code
    assert translated.detail["recovery"] == recovery
    assert translated.detail["correlation_id"] is None
    message = translated.detail["message"].lower()
    assert "sql" not in message
    assert "provider payload" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"branch_id": uuid4()},
        {"opened_by_user_id": uuid4()},
        {"status": "invented"},
        {"status": "resolved"},
        {
            "status": "open",
            "resolved_by_user_id": uuid4(),
            "resolved_at": datetime.now(timezone.utc),
        },
        {"evidence_digest": "short"},
    ],
)
async def test_reconciliation_exception_authority_fails_closed(
    payment_fixture, invalid_fields
) -> None:
    factory, company, branch, actor, _ = payment_fixture
    values = {
        "company_id": company.id,
        "branch_id": branch.id,
        "entity_type": "paymentintent",
        "entity_id": uuid4(),
        "reason_code": "synthetic_authority_test",
        "status": "open",
        "idempotency_key": f"authority-{uuid4()}",
        "evidence_digest": "a" * 64,
        "opened_by_user_id": actor.id,
        **invalid_fields,
    }
    async with factory() as session:
        session.add(ReconciliationException(**values))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_payment_receipt_refund_and_deposit_lineage_fails_closed(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    async with factory() as session:
        intent = await service.collect(
            session,
            CreateIntent(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                amount=Decimal("90.00"),
                currency="USD",
                opaque_payment_method="opaque_captured_test",
                idempotency_key=f"lineage-source-{uuid4()}",
                actor_user_id=actor.id,
            ),
        )
    async with factory() as session:
        receipt = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.intent_id == intent.id)
        )
        assert receipt is not None
    async with factory() as session:
        refund = await service.request_refund(
            session,
            RequestRefund(
                company_id=company.id,
                branch_id=branch.id,
                receipt_id=receipt.id,
                amount=Decimal("10.00"),
                reason="Synthetic lineage qualification",
                idempotency_key=f"lineage-refund-{uuid4()}",
                actor_user_id=actor.id,
                expected_version=receipt.version,
            ),
        )
    async with factory() as session:
        deposit = await service.create_deposit(
            session,
            CreateDeposit(
                company_id=company.id,
                branch_id=branch.id,
                receipt_ids=(receipt.id,),
                currency="USD",
                destination_reference="synthetic-clearing",
                idempotency_key=f"lineage-deposit-{uuid4()}",
                actor_user_id=actor.id,
            ),
        )

    for model, identity, changes in (
        (PaymentReceipt, receipt.id, {"branch_id": uuid4()}),
        (Refund, refund.id, {"branch_id": uuid4()}),
        (Deposit, deposit.id, {"branch_id": uuid4()}),
    ):
        async with factory() as session:
            with pytest.raises(IntegrityError):
                await session.execute(
                    update(model).where(model.id == identity).values(**changes)
                )
                await session.commit()

    async with factory() as session:
        membership = await session.scalar(
            select(DepositReceipt).where(DepositReceipt.deposit_id == deposit.id)
        )
        assert membership is not None
        with pytest.raises(IntegrityError):
            await session.execute(
                update(DepositReceipt)
                .where(DepositReceipt.id == membership.id)
                .values(currency="EUR")
            )
            await session.commit()


@pytest_asyncio.fixture
async def payment_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Payment concurrency",
            code=f"PAY{uuid4().hex[:7].upper()}",
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
        actor = User(
            normalized_email=f"payment-{uuid4().hex}@example.test",
            first_name="Payment",
            last_name="Operator",
            display_name="Payment Operator",
            status="active",
        )
        customer = Customer(
            company=company,
            customer_number=f"CUS-{uuid4().int % 1000000:06d}",
            status="active",
            customer_type="residential",
            display_name="Payment Customer",
            preferred_contact_method="email",
            normalized_name=f"payment customer {uuid4().hex}",
        )
        session.add_all([company, branch, actor, customer])
        await session.flush()
    try:
        yield factory, company, branch, actor, customer
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_collection_and_refund_replay_have_one_economic_authority(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture
    provider = CountingFakeProvider()
    service = PaymentService(provider, "synthetic-merchant")
    collect = CreateIntent(
        company_id=company.id,
        branch_id=branch.id,
        customer_id=customer.id,
        amount=Decimal("125.25"),
        currency="USD",
        opaque_payment_method="opaque_captured_test",
        idempotency_key=f"collect-{uuid4()}",
        actor_user_id=actor.id,
    )

    async def collect_once():
        async with factory() as session:
            return await service.collect(session, collect)

    first, replay = await asyncio.gather(collect_once(), collect_once())
    assert first.id == replay.id
    assert first.provider_operation_id == replay.provider_operation_id
    assert len(set(provider.collect_keys)) == 1
    async with factory() as session:
        intent = await session.get(PaymentIntent, first.id)
        receipt = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.intent_id == first.id)
        )
        assert intent is not None and intent.status == "captured"
        assert receipt is not None and receipt.available_amount == Decimal("125.25")
        assert (
            await session.scalar(
                select(func.count(PaymentIntent.id)).where(
                    PaymentIntent.company_id == company.id,
                    PaymentIntent.idempotency_key == collect.idempotency_key,
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.entity_id == first.id,
                    BusinessEvent.event_type == "payment.intent_created",
                )
            )
            == 1
        )

    refund = RequestRefund(
        company_id=company.id,
        branch_id=branch.id,
        receipt_id=receipt.id,
        amount=Decimal("25.25"),
        reason="Synthetic customer refund",
        idempotency_key=f"refund-{uuid4()}",
        actor_user_id=actor.id,
        expected_version=receipt.version,
    )

    async def refund_once():
        async with factory() as session:
            return await service.request_refund(session, refund)

    first_refund, refund_replay = await asyncio.gather(refund_once(), refund_once())
    assert first_refund.id == refund_replay.id
    assert first_refund.provider_operation_id == refund_replay.provider_operation_id
    assert len(set(provider.refund_keys)) == 1
    async with factory() as session:
        stored_receipt = await session.get(PaymentReceipt, receipt.id)
        assert stored_receipt is not None
        assert stored_receipt.refunded_amount == Decimal("25.25")
        assert stored_receipt.available_amount == Decimal("100.00")
        assert (
            await session.scalar(
                select(func.count(Refund.id)).where(
                    Refund.company_id == company.id,
                    Refund.idempotency_key == refund.idempotency_key,
                )
            )
            == 1
        )

    async with factory() as session:
        with pytest.raises(PaymentConflict, match="Idempotency key conflicts"):
            await service.collect(
                session,
                replace(collect, amount=Decimal("126.25")),
            )


@pytest.mark.asyncio
async def test_collection_replay_resumes_after_process_loss_before_provider_call(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture

    class SimulatedProcessLoss(BaseException):
        pass

    class ProcessLossProvider(CountingFakeProvider):
        async def collect(self, _request):
            raise SimulatedProcessLoss

    service = PaymentService(ProcessLossProvider(), "synthetic-merchant")
    command = CreateIntent(
        company_id=company.id,
        branch_id=branch.id,
        customer_id=customer.id,
        amount=Decimal("65.00"),
        currency="USD",
        opaque_payment_method="opaque_captured_test",
        idempotency_key=f"collection-loss-{uuid4()}",
        actor_user_id=actor.id,
    )

    async with factory() as session:
        with pytest.raises(SimulatedProcessLoss):
            await service.collect(session, command)
    async with factory() as session:
        pending = await session.scalar(
            select(PaymentIntent).where(
                PaymentIntent.idempotency_key == command.idempotency_key
            )
        )
        assert pending is not None and pending.status == "created"

    recovery_provider = CountingFakeProvider()
    service.provider = recovery_provider
    async with factory() as session:
        recovered = await service.collect(session, command)
    assert recovered.status == "captured"
    assert recovery_provider.collect_calls == 1
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(PaymentReceipt.id)).where(
                    PaymentReceipt.intent_id == recovered.id
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_collection_transport_uncertainty_reconciles_without_retry(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture

    class UncertainProvider(CountingFakeProvider):
        async def collect(self, _request):
            self.collect_calls += 1
            raise TimeoutError("synthetic possible collection acceptance")

    provider = UncertainProvider()
    service = PaymentService(provider, "synthetic-merchant")
    command = CreateIntent(
        company_id=company.id,
        branch_id=branch.id,
        customer_id=customer.id,
        amount=Decimal("70.00"),
        currency="USD",
        opaque_payment_method="opaque_captured_test",
        idempotency_key=f"collection-uncertain-{uuid4()}",
        actor_user_id=actor.id,
    )

    async with factory() as session:
        uncertain = await service.collect(session, command)
    async with factory() as session:
        replay = await service.collect(session, command)
    assert uncertain.id == replay.id
    assert replay.status == "reconciliation_required"
    assert provider.collect_calls == 1
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(PaymentReceipt.id)).where(
                    PaymentReceipt.intent_id == uncertain.id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(ReconciliationException.id)).where(
                    ReconciliationException.entity_id == uncertain.id,
                    ReconciliationException.reason_code
                    == "uncertain_collection_submission",
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_refund_replay_resumes_after_process_loss_before_provider_call(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture

    class SimulatedProcessLoss(BaseException):
        pass

    class ProcessLossProvider(CountingFakeProvider):
        async def refund(self, _request):
            raise SimulatedProcessLoss

    service = PaymentService(ProcessLossProvider(), "synthetic-merchant")
    async with factory() as session:
        intent = await service.collect(
            session,
            CreateIntent(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                amount=Decimal("45.00"),
                currency="USD",
                opaque_payment_method="opaque_captured_test",
                idempotency_key=f"loss-source-{uuid4()}",
                actor_user_id=actor.id,
            ),
        )
    async with factory() as session:
        receipt = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.intent_id == intent.id)
        )
        assert receipt is not None
    command = RequestRefund(
        company_id=company.id,
        branch_id=branch.id,
        receipt_id=receipt.id,
        amount=Decimal("15.00"),
        reason="Synthetic process-loss recovery",
        idempotency_key=f"loss-refund-{uuid4()}",
        actor_user_id=actor.id,
        expected_version=receipt.version,
    )

    async with factory() as session:
        with pytest.raises(SimulatedProcessLoss):
            await service.request_refund(session, command)
    async with factory() as session:
        pending = await session.scalar(
            select(Refund).where(Refund.idempotency_key == command.idempotency_key)
        )
        assert pending is not None and pending.status == "requested"

    recovery_provider = CountingFakeProvider()
    service.provider = recovery_provider
    async with factory() as session:
        recovered = await service.request_refund(session, command)
    assert recovered.status == "succeeded"
    assert recovery_provider.refund_calls == 1
    async with factory() as session:
        stored_receipt = await session.get(PaymentReceipt, receipt.id)
        assert stored_receipt is not None
        assert stored_receipt.available_amount == Decimal("30.00")
        assert stored_receipt.refunded_amount == Decimal("15.00")


@pytest.mark.asyncio
async def test_refund_transport_uncertainty_requires_reconciliation_without_retry(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture

    class UncertainProvider(CountingFakeProvider):
        async def refund(self, _request):
            self.refund_calls += 1
            raise TimeoutError("synthetic possible acceptance")

    provider = UncertainProvider()
    service = PaymentService(provider, "synthetic-merchant")
    async with factory() as session:
        intent = await service.collect(
            session,
            CreateIntent(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                amount=Decimal("55.00"),
                currency="USD",
                opaque_payment_method="opaque_captured_test",
                idempotency_key=f"uncertain-source-{uuid4()}",
                actor_user_id=actor.id,
            ),
        )
    async with factory() as session:
        receipt = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.intent_id == intent.id)
        )
        assert receipt is not None
    command = RequestRefund(
        company_id=company.id,
        branch_id=branch.id,
        receipt_id=receipt.id,
        amount=Decimal("10.00"),
        reason="Synthetic uncertain refund",
        idempotency_key=f"uncertain-refund-{uuid4()}",
        actor_user_id=actor.id,
        expected_version=receipt.version,
    )

    async with factory() as session:
        uncertain = await service.request_refund(session, command)
    async with factory() as session:
        replay = await service.request_refund(session, command)
    assert uncertain.id == replay.id
    assert replay.status == "reconciliation_required"
    assert provider.refund_calls == 1
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(ReconciliationException.id)).where(
                    ReconciliationException.entity_id == uncertain.id,
                    ReconciliationException.reason_code
                    == "uncertain_refund_submission",
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_collection_rejects_foreign_company_customer_before_provider_call(
    payment_fixture,
) -> None:
    factory, company, branch, actor, _ = payment_fixture
    async with factory() as session, session.begin():
        foreign_company = Company(
            name="Foreign Payment Company",
            code=f"FP{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        foreign_customer = Customer(
            company=foreign_company,
            customer_number=f"CUS-{uuid4().int % 1000000:06d}",
            status="active",
            customer_type="residential",
            display_name="Foreign Payment Customer",
            preferred_contact_method="email",
            normalized_name=f"foreign payment customer {uuid4().hex}",
        )
        session.add_all([foreign_company, foreign_customer])
        await session.flush()

    provider = CountingFakeProvider()
    service = PaymentService(provider, "synthetic-merchant")
    command = CreateIntent(
        company_id=company.id,
        branch_id=branch.id,
        customer_id=foreign_customer.id,
        amount=Decimal("19.99"),
        currency="USD",
        opaque_payment_method="opaque_captured_test",
        idempotency_key=f"foreign-customer-{uuid4()}",
        actor_user_id=actor.id,
    )
    async with factory() as session:
        with pytest.raises(PaymentNotFound, match="Customer was not found"):
            await service.collect(session, command)

    assert provider.collect_calls == 0
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(PaymentIntent.id)).where(
                    PaymentIntent.company_id == company.id,
                    PaymentIntent.idempotency_key == command.idempotency_key,
                )
            )
            == 0
        )

    async with factory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    PaymentIntent(
                        company_id=company.id,
                        branch_id=branch.id,
                        customer_id=foreign_customer.id,
                        amount=Decimal("19.99"),
                        currency="USD",
                        provider="synthetic",
                        merchant_account="synthetic-merchant",
                        opaque_payment_method="opaque_corruption_canary",
                        idempotency_key=f"corrupt-{uuid4()}",
                        request_digest="1" * 64,
                        provider_idempotency_key=f"pay_{uuid4().hex}",
                        created_by_user_id=actor.id,
                    )
                )
                await session.flush()


@pytest.mark.asyncio
async def test_ambiguous_provider_outcome_is_reconciled_without_blind_retry(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture
    provider = CountingFakeProvider()
    service = PaymentService(provider, "synthetic-merchant")
    command = CreateIntent(
        company_id=company.id,
        branch_id=branch.id,
        customer_id=customer.id,
        amount=Decimal("41.00"),
        currency="USD",
        opaque_payment_method="opaque_ambiguous_after_acceptance",
        idempotency_key=f"ambiguous-{uuid4()}",
        actor_user_id=actor.id,
    )
    async with factory() as session:
        first = await service.collect(session, command)
    async with factory() as session:
        replay = await service.collect(session, command)
    assert first.id == replay.id
    assert first.status == replay.status == "reconciliation_required"
    assert provider.collect_calls == 1
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(PaymentReceipt.id)).where(
                    PaymentReceipt.intent_id == first.id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(ReconciliationException.id)).where(
                    ReconciliationException.entity_id == first.id,
                    ReconciliationException.reason_code
                    == "ambiguous_processor_outcome",
                )
            )
            == 1
        )
@pytest.mark.asyncio
async def test_concurrent_identical_application_changes_receipt_once(
    payment_fixture, monkeypatch
) -> None:
    factory, company, branch, actor, customer = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    async with factory() as session:
        intent = await service.collect(
            session,
            CreateIntent(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                amount=Decimal("80.00"),
                currency="USD",
                opaque_payment_method="opaque_captured_test",
                idempotency_key=f"apply-source-{uuid4()}",
                actor_user_id=actor.id,
            ),
        )
    async with factory() as session:
        receipt = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.intent_id == intent.id)
        )
        assert receipt is not None

    first_entered = asyncio.Event()
    release = asyncio.Event()

    class ConcurrentInvoiceService:
        calls = 0

        async def apply_payment_in_transaction(self, _session, fact):
            self.calls += 1
            first_entered.set()
            await release.wait()
            return SimpleNamespace(id=fact.invoice_id)

    invoice_boundary = ConcurrentInvoiceService()
    monkeypatch.setattr("app.payments.service.invoice_service", invoice_boundary)
    command = ApplyReceipt(
        company_id=company.id,
        branch_id=branch.id,
        receipt_id=receipt.id,
        invoice_id=uuid4(),
        amount=Decimal("30.00"),
        expected_invoice_version=1,
        idempotency_key=f"apply-{uuid4()}",
        actor_user_id=actor.id,
        occurred_at=receipt.captured_at,
    )

    async def apply_once() -> PaymentReceipt:
        async with factory() as session:
            return await service.apply(session, command)

    first_task = asyncio.create_task(apply_once())
    await asyncio.wait_for(first_entered.wait(), timeout=2)
    replay_task = asyncio.create_task(apply_once())
    await asyncio.sleep(0.05)
    assert invoice_boundary.calls == 1
    release.set()
    first, replay = await asyncio.gather(first_task, replay_task)
    assert first.id == replay.id == receipt.id
    assert invoice_boundary.calls == 1

    async with factory() as session:
        stored = await session.get(PaymentReceipt, receipt.id)
        assert stored is not None
        assert stored.applied_amount == Decimal("30.00")
        assert stored.available_amount == Decimal("50.00")
        assert (
            await session.scalar(
                select(func.count(ReceiptEvent.id)).where(
                    ReceiptEvent.receipt_id == receipt.id,
                    ReceiptEvent.idempotency_key == command.idempotency_key,
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_application_failure_rolls_back_both_domain_mutations(
    payment_fixture, monkeypatch
) -> None:
    factory, company, branch, actor, customer = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    async with factory() as session:
        intent = await service.collect(
            session,
            CreateIntent(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                amount=Decimal("80.00"),
                currency="USD",
                opaque_payment_method="opaque_captured_test",
                idempotency_key=f"failure-source-{uuid4()}",
                actor_user_id=actor.id,
            ),
        )
    async with factory() as session:
        receipt = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.intent_id == intent.id)
        )
        assert receipt is not None

    class FailingInvoiceService:
        async def apply_payment_in_transaction(self, session, _fact):
            locked = await session.get(PaymentReceipt, receipt.id)
            assert locked is not None
            locked.available_amount = Decimal("50.00")
            locked.applied_amount = Decimal("30.00")
            await session.flush()
            raise InvoiceError("synthetic failure after invoice mutation")

    monkeypatch.setattr(
        "app.payments.service.invoice_service", FailingInvoiceService()
    )
    command = ApplyReceipt(
        company_id=company.id,
        branch_id=branch.id,
        receipt_id=receipt.id,
        invoice_id=uuid4(),
        amount=Decimal("30.00"),
        expected_invoice_version=1,
        idempotency_key=f"failure-apply-{uuid4()}",
        actor_user_id=actor.id,
        occurred_at=receipt.captured_at,
    )

    async with factory() as session:
        with pytest.raises(PaymentConflict):
            await service.apply(session, command)

    async with factory() as session:
        stored = await session.get(PaymentReceipt, receipt.id)
        assert stored is not None
        assert stored.available_amount == Decimal("80.00")
        assert stored.applied_amount == Decimal("0.00")
        assert (
            await session.scalar(
                select(func.count(ReceiptEvent.id)).where(
                    ReceiptEvent.receipt_id == receipt.id,
                    ReceiptEvent.idempotency_key == command.idempotency_key,
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_payment_posting_receipt_replay_binds_complete_authority(
    payment_fixture,
) -> None:
    factory, company, _, _, _ = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    fact = PostingReceiptFact(
        company_id=company.id,
        source_event_id=uuid4(),
        journal_id=uuid4(),
        journal_version=3,
        policy_version="cash-basis-v3",
        status="posted",
        effective_date=date(2026, 8, 30),
        posted_at=datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc),
    )
    async with factory() as session:
        first = await service.record_posting_receipt(session, fact)
    async with factory() as session:
        replay = await service.record_posting_receipt(session, fact)
    assert replay.id == first.id

    contradictions = (
        replace(fact, journal_id=uuid4()),
        replace(fact, journal_version=4),
        replace(fact, policy_version="cash-basis-v4"),
        replace(fact, status="reconciliation_required"),
        replace(fact, effective_date=date(2026, 8, 31)),
        replace(
            fact,
            posted_at=datetime(2026, 8, 30, 18, 1, tzinfo=timezone.utc),
        ),
    )
    for contradiction in contradictions:
        async with factory() as session:
            with pytest.raises(PaymentConflict, match="conflicts with replay"):
                await service.record_posting_receipt(session, contradiction)


@pytest.mark.asyncio
async def test_dispute_replay_binds_amount_provider_and_evidence(payment_fixture) -> None:
    factory, company, branch, actor, customer = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    async with factory() as session:
        intent = await service.collect(
            session,
            CreateIntent(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=customer.id,
                amount=Decimal("90.00"),
                currency="USD",
                opaque_payment_method="opaque_captured_test",
                idempotency_key=f"dispute-source-{uuid4()}",
                actor_user_id=actor.id,
            ),
        )
    async with factory() as session:
        receipt = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.intent_id == intent.id)
        )
        assert receipt is not None

    command = RecordDispute(
        company_id=company.id,
        branch_id=branch.id,
        receipt_id=receipt.id,
        amount=Decimal("20.00"),
        provider_dispute_id="provider-dispute-1001",
        evidence_digest="a" * 64,
        idempotency_key=f"dispute-{uuid4()}",
        actor_user_id=actor.id,
        expected_version=receipt.version,
    )
    async with factory() as session:
        first = await service.record_dispute(session, command)
    async with factory() as session:
        replay = await service.record_dispute(session, command)
    assert replay.id == first.id
    assert replay.disputed_amount == Decimal("20.00")
    assert replay.available_amount == Decimal("70.00")

    contradictions = (
        replace(command, amount=Decimal("21.00")),
        replace(command, provider_dispute_id="provider-dispute-1002"),
        replace(command, evidence_digest="b" * 64),
    )
    for contradiction in contradictions:
        async with factory() as session:
            with pytest.raises(PaymentConflict, match="original dispute"):
                await service.record_dispute(session, contradiction)

    async with factory() as session:
        event = await session.scalar(
            select(ReceiptEvent).where(
                ReceiptEvent.receipt_id == receipt.id,
                ReceiptEvent.idempotency_key == command.idempotency_key,
            )
        )
        assert event is not None
        assert event.provider_reference == command.provider_dispute_id
        assert event.request_digest is not None and len(event.request_digest) == 64


@pytest.mark.asyncio
async def test_settlement_replay_binds_complete_economic_evidence(
    payment_fixture,
) -> None:
    factory, company, _, actor, _ = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    command = RecordSettlement(
        company_id=company.id,
        provider="deterministic_fake",
        merchant_account="synthetic-merchant",
        provider_payout_id=f"payout-{uuid4()}",
        currency="USD",
        settlement_date=date(2026, 8, 30),
        gross_amount=Decimal("100.00"),
        refund_amount=Decimal("10.00"),
        dispute_amount=Decimal("5.00"),
        fee_amount=Decimal("2.00"),
        adjustment_amount=Decimal("1.00"),
        net_amount=Decimal("84.00"),
        evidence_digest="d" * 64,
        actor_user_id=actor.id,
    )
    async with factory() as session:
        first = await service.record_settlement(session, command)
    async with factory() as session:
        replay = await service.record_settlement(session, command)
    assert replay.id == first.id

    contradictions = (
        replace(command, currency="CAD"),
        replace(command, settlement_date=date(2026, 8, 31)),
        replace(
            command,
            gross_amount=Decimal("101.00"),
            net_amount=Decimal("85.00"),
        ),
        replace(
            command,
            refund_amount=Decimal("11.00"),
            net_amount=Decimal("83.00"),
        ),
        replace(
            command,
            dispute_amount=Decimal("6.00"),
            net_amount=Decimal("83.00"),
        ),
        replace(
            command,
            fee_amount=Decimal("3.00"),
            net_amount=Decimal("83.00"),
        ),
        replace(
            command,
            adjustment_amount=Decimal("2.00"),
            net_amount=Decimal("85.00"),
        ),
        replace(command, evidence_digest="e" * 64),
    )
    for contradiction in contradictions:
        async with factory() as session:
            with pytest.raises(PaymentConflict, match="conflicts with replay"):
                await service.record_settlement(session, contradiction)


@pytest.mark.asyncio
async def test_webhook_contradiction_persists_one_reconciliation_exception(
    payment_fixture,
) -> None:
    factory, company, _, _, _ = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    evidence = VerifiedWebhook(
        provider_event_id=f"event-{uuid4()}",
        merchant_account="synthetic-merchant",
        event_type="payment.captured",
        occurred_at=datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc),
        allowed_evidence={"amount": "25.00", "currency": "USD"},
        evidence_digest="f" * 64,
        secret_version="v1",
    )
    async with factory() as session:
        first = await service.record_webhook(
            session, company.id, "deterministic_fake", evidence
        )
    async with factory() as session:
        replay = await service.record_webhook(
            session, company.id, "deterministic_fake", evidence
        )
    assert replay.id == first.id

    contradiction = replace(
        evidence,
        event_type="payment.refunded",
        allowed_evidence={"amount": "26.00", "currency": "USD"},
        evidence_digest="0" * 64,
        secret_version="v2",
    )
    for _ in range(2):
        async with factory() as session:
            with pytest.raises(PaymentConflict, match="conflicts with prior evidence"):
                await service.record_webhook(
                    session, company.id, "deterministic_fake", contradiction
                )

    async with factory() as session:
        exception = await session.scalar(
            select(ReconciliationException).where(
                ReconciliationException.entity_type == "webhook",
                ReconciliationException.entity_id == first.id,
                ReconciliationException.reason_code
                == "contradictory_provider_event",
            )
        )
        assert exception is not None
        assert exception.evidence_digest == contradiction.evidence_digest
        assert (
            await session.scalar(
                select(func.count(ReconciliationException.id)).where(
                    ReconciliationException.entity_type == "webhook",
                    ReconciliationException.entity_id == first.id,
                    ReconciliationException.reason_code
                    == "contradictory_provider_event",
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.entity_type == "payment_reconciliation_exception",
                    BusinessEvent.entity_id == exception.id,
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_receipt_listing_is_stably_bounded_and_service_enforced(
    payment_fixture,
) -> None:
    factory, company, branch, actor, customer = payment_fixture
    service = PaymentService(CountingFakeProvider(), "synthetic-merchant")
    receipt_ids: set[UUID] = set()
    for position in range(3):
        async with factory() as session:
            intent = await service.collect(
                session,
                CreateIntent(
                    company_id=company.id,
                    branch_id=branch.id,
                    customer_id=customer.id,
                    amount=Decimal("10.00") + position,
                    currency="USD",
                    opaque_payment_method="opaque_captured_test",
                    idempotency_key=f"list-receipt-{uuid4()}",
                    actor_user_id=actor.id,
                ),
            )
        async with factory() as session:
            receipt_id = await session.scalar(
                select(PaymentReceipt.id).where(PaymentReceipt.intent_id == intent.id)
            )
            assert receipt_id is not None
            receipt_ids.add(receipt_id)

    async with factory() as session:
        first_page = await service.list_receipts(
            session,
            company.id,
            frozenset({branch.id}),
            limit=2,
            offset=0,
        )
        second_page = await service.list_receipts(
            session,
            company.id,
            frozenset({branch.id}),
            limit=2,
            offset=2,
        )
    assert len(first_page) == 2
    assert {row.id for row in first_page}.isdisjoint(
        {row.id for row in second_page}
    )
    assert receipt_ids.issubset(
        {row.id for row in first_page} | {row.id for row in second_page}
    )

    async with factory() as session:
        with pytest.raises(PaymentValidation, match="page is invalid"):
            await service.list_receipts(
                session,
                company.id,
                frozenset({branch.id}),
                limit=201,
            )
