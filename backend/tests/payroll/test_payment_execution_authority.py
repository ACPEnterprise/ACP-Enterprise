from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.models import BusinessEvent
from app.payroll.contracts import (
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from app.payroll.models import PayrollPaymentExecutionItemRecord
from app.payroll.payment_execution import (
    InstructionExecutionState,
    PayrollPaymentExecutionService,
    ProviderAcknowledgement,
    ProviderResultState,
    SettlementItemEvidence,
    SyntheticPaymentExecutionProvider,
)
from app.payroll.payment_release import (
    DestinationAdmissionState,
    PaymentReleaseReviewDecision,
)
from app.payroll.permissions import PayrollPermission
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_release_authority import (
    approved_run,
    contexts,
    destination,
    payment_service,
)

finalization_database = _database
NOW = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)


async def approved_release(session: AsyncSession, values: dict[str, object]):  # type: ignore[no-untyped-def]
    release_service = payment_service()
    manage, assemble, review, approve_read = contexts(values)
    run, _ = await approved_run(session, values)
    await destination(session, release_service, manage, values["employee_id"])
    resolution = await release_service.resolve_destination(session, company_id=values["company_id"], employee_id=values["employee_id"], as_of_date=NOW.date())
    assert resolution.state is DestinationAdmissionState.READY
    candidate = await release_service.assemble_candidate(session, context=assemble, payroll_run_id=run.id, destinations={values["employee_id"]: resolution}, assembled_at=NOW)
    release = await release_service.persist_candidate(session, context=assemble, candidate=candidate)
    await release_service.initiate_review(session, context=review, release_id=release.id, reason_code="synthetic")
    await release_service.decide_review(session, context=review, release_id=release.id, decision=PaymentReleaseReviewDecision.ACCEPTED, reason_code="synthetic")
    await release_service.approve_release(session, context=approve_read, release_id=release.id, reason_code="synthetic")
    await session.refresh(release)
    return release


def execution_contexts(values: dict[str, object]) -> tuple[Any, Any, Any]:
    authorize = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE})
    reconcile = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.PAYMENT_SETTLEMENT_RECONCILE})
    read = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.PAYMENT_EXECUTION_READ})
    return authorize, reconcile, read


async def authorized_execution(session: AsyncSession, values: dict[str, object]):  # type: ignore[no-untyped-def]
    release = await approved_release(session, values)
    service = PayrollPaymentExecutionService()
    authorize, _, _ = execution_contexts(values)
    candidate = await service.create_candidate(session, context=authorize, release_id=release.id, provider_identity="synthetic.payment-provider", provider_version="test.v1", idempotency_identity="synthetic-idempotency-1")
    execution = await service.authorize(session, context=authorize, candidate=candidate)
    return service, release, candidate, execution


@pytest.mark.asyncio
async def test_execution_acknowledgement_settlement_handoff_and_safe_events(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        service, release, candidate, execution = await authorized_execution(session, values)
        authorize, reconcile, read = execution_contexts(values)
        with pytest.raises(PayrollConflictError, match="candidate"):
            await service.authorize(
                session,
                context=authorize,
                candidate=replace(
                    candidate, authorized_total=candidate.authorized_total + Decimal("1.00")
                ),
            )
        replay = await service.authorize(session, context=authorize, candidate=candidate)
        assert replay.id == execution.id
        provider = SyntheticPaymentExecutionProvider(environment="test")
        acknowledged = await service.submit(session, context=authorize, execution_id=execution.id, provider=provider)
        assert acknowledged.lifecycle == "provider_acknowledged" and provider.calls == 1
        retried = await service.submit(session, context=authorize, execution_id=execution.id, provider=provider)
        assert retried.id == execution.id and provider.calls == 1
        with pytest.raises(PayrollConflictError, match="settlement evidence"):
            await service.accounting_handoff(session, context=read, execution_id=execution.id)
        item = await session.scalar(select(PayrollPaymentExecutionItemRecord).where(PayrollPaymentExecutionItemRecord.execution_id == execution.id))
        assert item is not None
        reference = "synthetic-settlement-reference"
        digest = canonical_digest({"instruction_id": str(item.instruction_id), "state": "settled", "provider_safe_reference": reference})
        settled = await service.record_settlement(session, context=reconcile, execution_id=execution.id, outcomes=(SettlementItemEvidence(item.instruction_id, InstructionExecutionState.SETTLED, reference, digest),), occurred_at=NOW)
        assert settled.lifecycle == "settled"
        handoff = await service.accounting_handoff(session, context=read, execution_id=execution.id)
        assert handoff.settled_total == release.aggregate_release_amount
        events = tuple((await session.scalars(select(BusinessEvent).where(BusinessEvent.entity_type == "payroll_payment_execution"))).all())
        assert events and all("amount" not in str(event.payload) and "destination" not in str(event.payload) for event in events)


@pytest.mark.asyncio
async def test_rejection_uncertain_contradiction_permissions_and_company_scope(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        service, release, _candidate, execution = await authorized_execution(session, values)
        authorize, reconcile, _ = execution_contexts(values)
        no_permission = FakeContext(values["company_id"], values["actor_id"], set())
        with pytest.raises(PayrollAuthorizationError):
            await service.create_candidate(session, context=no_permission, release_id=release.id, provider_identity="synthetic.payment-provider", provider_version="test.v1", idempotency_identity="denied")
        other_company = FakeContext(values["other_company_id"], values["actor_id"], {PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE})
        with pytest.raises(PayrollConflictError, match="approved-for-release"):
            await service.create_candidate(session, context=other_company, release_id=release.id, provider_identity="synthetic.payment-provider", provider_version="test.v1", idempotency_identity="cross-company")
        uncertain = SyntheticPaymentExecutionProvider(environment="test", result=ProviderResultState.UNCERTAIN)
        result = await service.submit(session, context=authorize, execution_id=execution.id, provider=uncertain)
        assert result.lifecycle == "uncertain" and uncertain.calls == 1
        with pytest.raises(PayrollConflictError, match="submit-ready"):
            await service.submit(session, context=authorize, execution_id=execution.id, provider=uncertain)
        contradictory = ProviderAcknowledgement(ProviderResultState.ACCEPTED, "different-safe-reference", NOW, result.request_digest or "", canonical_digest({"different": True}))
        with pytest.raises(PayrollConflictError, match="contradictory"):
            await service.record_acknowledgement(session, context=authorize, execution_id=execution.id, acknowledgement=contradictory)
        with pytest.raises(PayrollConflictError, match="acknowledged"):
            await service.record_settlement(session, context=reconcile, execution_id=execution.id, outcomes=(), occurred_at=NOW)


@pytest.mark.asyncio
async def test_failed_settlement_and_test_only_provider(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    with pytest.raises(PayrollConflictError, match="test-only"):
        SyntheticPaymentExecutionProvider(environment="production")
    factory, values = finalization_database
    async with factory() as session:
        service, _, _, execution = await authorized_execution(session, values)
        authorize, reconcile, _ = execution_contexts(values)
        provider = SyntheticPaymentExecutionProvider(environment="test")
        await service.submit(session, context=authorize, execution_id=execution.id, provider=provider)
        item = await session.scalar(select(PayrollPaymentExecutionItemRecord).where(PayrollPaymentExecutionItemRecord.execution_id == execution.id))
        assert item is not None
        reference = "synthetic-failed-settlement"
        digest = canonical_digest({"instruction_id": str(item.instruction_id), "state": "failed", "provider_safe_reference": reference})
        failed = await service.record_settlement(session, context=reconcile, execution_id=execution.id, outcomes=(SettlementItemEvidence(item.instruction_id, InstructionExecutionState.FAILED, reference, digest),), occurred_at=NOW)
        assert failed.lifecycle == "failed"
