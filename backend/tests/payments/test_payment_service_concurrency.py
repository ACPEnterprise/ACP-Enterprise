import asyncio
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import Customer
from app.events.models import BusinessEvent
from app.payments.contracts import CreateIntent, ProviderRequest, RequestRefund
from app.payments.errors import PaymentConflict, PaymentNotFound, PaymentValidation
from app.payments.models import (
    PaymentIntent,
    PaymentReceipt,
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

    async def collect(self, request: ProviderRequest):
        self.collect_calls += 1
        return await super().collect(request)


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
    assert provider.collect_calls == 1
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
