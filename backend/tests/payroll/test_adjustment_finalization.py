from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customers.models import Customer  # noqa: F401
from app.payroll.adjustment_calculation import (
    AuthorizedDeltaRuleProvider,
    PayrollAdjustmentCalculationService,
    RuleEnvironment,
)
from app.payroll.adjustment_finalization import (
    AdjustmentResultDecision,
    PayrollAdjustmentResultService,
)
from app.payroll.contracts import PayrollAuthorizationError, PayrollConflictError
from app.payroll.models import (
    PayrollAdjustmentApplicationRecord,
    PayrollAdjustmentResultReviewRecord,
)
from app.payroll.permissions import PayrollPermission
from app.scheduling.models import Appointment  # noqa: F401
from tests.payroll.test_adjustment_authority import draft
from tests.payroll.test_adjustment_calculation import approved_adjustment
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_release_authority import approved_run

finalization_database = _database


def context(values: dict[str, object], permission: str, *, other: bool = False) -> Any:
    return FakeContext(values["other_company_id"] if other else values["company_id"], values["actor_id"], {permission})


async def candidate_and_authority(session: AsyncSession, values: dict[str, object]):  # type: ignore[no-untyped-def]
    run, _ = await approved_run(session, values)
    authority = await approved_adjustment(session, values, draft(run))
    candidate = await PayrollAdjustmentCalculationService(runtime_environment=RuleEnvironment.TEST).calculate(session, context=context(values, PayrollPermission.ADJUSTMENT_CALCULATE), adjustment_id=authority.id, provider=AuthorizedDeltaRuleProvider())
    return run, authority, candidate


@pytest.mark.asyncio
async def test_persist_review_approve_apply_replay_and_safe_immutability(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, authority, candidate = await candidate_and_authority(session, values)
        original = (run.run_digest, run.lifecycle, authority.adjustment_digest)
        service = PayrollAdjustmentResultService()
        execute = context(values, PayrollPermission.ADJUSTMENT_CALCULATE)
        review = context(values, PayrollPermission.ADJUSTMENT_RESULT_REVIEW)
        approve = context(values, PayrollPermission.ADJUSTMENT_RESULT_APPROVE)
        apply = context(values, PayrollPermission.ADJUSTMENT_APPLY)
        first = await service.persist_candidate(session, context=execute, candidate=candidate)
        replay = await service.persist_candidate(session, context=execute, candidate=candidate)
        assert replay.id == first.id
        initiated = await service.initiate_review(session, context=review, result_id=first.id, reason_code="synthetic")
        await service.decide_review(session, context=review, result_id=first.id, decision=AdjustmentResultDecision.ACCEPTED, reason_code="synthetic")
        approved = await service.approve(session, context=approve, result_id=first.id, reason_code="synthetic")
        assert initiated.sequence == 1 and approved.sequence == 3
        application = await service.apply(session, context=apply, result_id=first.id, purpose="successor_payroll", successor_authority_type="payroll.gross-pay-successor.v1")
        application_replay = await service.apply(session, context=apply, result_id=first.id, purpose="successor_payroll", successor_authority_type="payroll.gross-pay-successor.v1")
        assert application.id == application_replay.id
        await session.refresh(run)
        await session.refresh(authority)
        assert (run.run_digest, run.lifecycle, authority.adjustment_digest) == original
        assert await session.scalar(select(func.count(PayrollAdjustmentApplicationRecord.id)).where(PayrollAdjustmentApplicationRecord.result_id == first.id)) == 1


@pytest.mark.asyncio
async def test_admission_tamper_unapproved_scope_and_permissions_fail_closed(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        _, authority, candidate = await candidate_and_authority(session, values)
        service = PayrollAdjustmentResultService()
        execute = context(values, PayrollPermission.ADJUSTMENT_CALCULATE)
        with pytest.raises(PayrollConflictError):
            await service.persist_candidate(session, context=execute, candidate=replace(candidate, currency="EUR"))
        authority.lifecycle = "draft"
        await session.flush()
        with pytest.raises(PayrollConflictError, match="approved"):
            await service.persist_candidate(session, context=execute, candidate=candidate)
        await session.rollback()
        with pytest.raises(PayrollConflictError):
            await service.persist_candidate(session, context=context(values, PayrollPermission.ADJUSTMENT_CALCULATE, other=True), candidate=candidate)
        with pytest.raises(PayrollAuthorizationError):
            await service.persist_candidate(session, context=FakeContext(values["company_id"], values["actor_id"], set()), candidate=candidate)


@pytest.mark.asyncio
async def test_rejection_history_and_unauthorized_approval(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        _, _, candidate = await candidate_and_authority(session, values)
        service = PayrollAdjustmentResultService()
        value = await service.persist_candidate(session, context=context(values, PayrollPermission.ADJUSTMENT_CALCULATE), candidate=candidate)
        review = context(values, PayrollPermission.ADJUSTMENT_RESULT_REVIEW)
        await service.initiate_review(session, context=review, result_id=value.id, reason_code="synthetic_reject")
        await service.decide_review(session, context=review, result_id=value.id, decision=AdjustmentResultDecision.REJECTED, reason_code="synthetic_reject")
        with pytest.raises(PayrollAuthorizationError):
            await service.approve(session, context=review, result_id=value.id, reason_code="no")
        history = tuple((await session.scalars(select(PayrollAdjustmentResultReviewRecord).where(PayrollAdjustmentResultReviewRecord.result_id == value.id))).all())
        assert [item.decision for item in history] == ["initiated", "rejected"]


@pytest.mark.asyncio
async def test_supersession_is_append_only_and_cannot_follow_application(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        _, _, candidate = await candidate_and_authority(session, values)
        service = PayrollAdjustmentResultService()
        execute = context(values, PayrollPermission.ADJUSTMENT_CALCULATE)
        first = await service.persist_candidate(session, context=execute, candidate=candidate)
        changed = replace(candidate, definition_version="payroll.adjustment-calculation.v2", calculation_digest="", result_identity="")
        from app.payroll.contracts import canonical_digest
        digest = canonical_digest(changed.canonical_content())
        changed = replace(changed, calculation_digest=digest, result_identity=f"payroll-adjustment-calculation:{digest}")
        second = await service.persist_candidate(session, context=execute, candidate=changed, supersedes_result_id=first.id)
        await session.refresh(first)
        assert first.lifecycle == "superseded" and second.supersedes_result_id == first.id
        forked = replace(changed, definition_version="payroll.adjustment-calculation.v3", calculation_digest="", result_identity="")
        digest = canonical_digest(forked.canonical_content())
        forked = replace(forked, calculation_digest=digest, result_identity=f"payroll-adjustment-calculation:{digest}")
        with pytest.raises(PayrollConflictError, match="lineage|active"):
            await service.persist_candidate(session, context=execute, candidate=forked, supersedes_result_id=first.id)
