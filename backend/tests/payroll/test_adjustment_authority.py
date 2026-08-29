from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customers.models import Customer  # noqa: F401
from app.payroll.adjustments import (
    AdjustmentReviewDecision,
    DraftPayrollAdjustment,
    EconomicDelta,
    PayrollAdjustmentService,
    PayrollCorrectionType,
)
from app.payroll.contracts import (
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from app.payroll.permissions import PayrollPermission
from app.scheduling.models import Appointment  # noqa: F401
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_execution_authority import authorized_execution
from tests.payroll.test_payment_release_authority import approved_run

finalization_database = _database


def contexts(values: dict[str, object]) -> tuple[Any, Any, Any, Any]:
    manage = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.ADJUSTMENT_MANAGE})
    review = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.ADJUSTMENT_REVIEW})
    approve = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.ADJUSTMENT_APPROVE})
    read = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.ADJUSTMENT_READ})
    return manage, review, approve, read


def draft(run, classification: PayrollCorrectionType = PayrollCorrectionType.RETROACTIVE_EARNINGS, *, amount: Decimal = Decimal("25.00"), supersedes=None):  # type: ignore[no-untyped-def]
    return DraftPayrollAdjustment(classification=classification, reason_code="synthetic_correction", source_type="payroll_run", source_id=run.id, source_digest=run.run_digest, currency=run.currency, effective_date=date(2026, 9, 15), evidence_digest=canonical_digest({"synthetic-evidence": str(amount)}), delta_components=(EconomicDelta("gross_wages", amount),), employee_id=None, original_pay_period_id=run.pay_period_id, off_cycle_pay_period_id=uuid4() if classification is PayrollCorrectionType.OFF_CYCLE_PAYROLL else None, supersedes_adjustment_id=supersedes)


@pytest.mark.asyncio
async def test_retroactive_negative_delta_review_approval_and_original_immutable(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        original_digest, original_lifecycle = run.run_digest, run.lifecycle
        service = PayrollAdjustmentService()
        manage, review, approve, read = contexts(values)
        command = draft(run, amount=Decimal("-12.50"))
        first = await service.create(session, context=manage, draft=command)
        replay = await service.create(session, context=manage, draft=command)
        assert replay.id == first.id and first.delta_components[0]["amount"] == "-12.50"
        await service.initiate_review(session, context=review, adjustment_id=first.id, reason_code="synthetic")
        await service.decide_review(session, context=review, adjustment_id=first.id, decision=AdjustmentReviewDecision.ACCEPTED, reason_code="synthetic")
        await service.approve(session, context=approve, adjustment_id=first.id, reason_code="synthetic")
        consequence = await service.consequence(session, context=read, adjustment_id=first.id)
        await session.refresh(run)
        assert consequence.requires_successor_payroll
        assert run.run_digest == original_digest and run.lifecycle == original_lifecycle


@pytest.mark.asyncio
async def test_off_cycle_competing_cross_company_and_permissions_fail_closed(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        service = PayrollAdjustmentService()
        manage, _, _, _ = contexts(values)
        command = draft(run, PayrollCorrectionType.OFF_CYCLE_PAYROLL)
        await service.create(session, context=manage, draft=command)
        with pytest.raises(PayrollConflictError, match="competing"):
            await service.create(session, context=manage, draft=DraftPayrollAdjustment(**{**command.__dict__, "evidence_digest": "b" * 64}))
        other = FakeContext(values["other_company_id"], values["actor_id"], {PayrollPermission.ADJUSTMENT_MANAGE})
        with pytest.raises(PayrollConflictError, match="source"):
            await service.create(session, context=other, draft=command)
        denied = FakeContext(values["company_id"], values["actor_id"], set())
        with pytest.raises(PayrollAuthorizationError):
            await service.create(session, context=denied, draft=command)


@pytest.mark.asyncio
async def test_payment_return_binds_execution_without_erasing_payment_evidence(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        _, _, _, execution = await authorized_execution(session, values)
        original_digest, original_state = execution.execution_digest, execution.lifecycle
        service = PayrollAdjustmentService()
        manage, _, _, _ = contexts(values)
        command = DraftPayrollAdjustment(classification=PayrollCorrectionType.PAYMENT_RETURN, reason_code="synthetic_return", source_type="payment_execution", source_id=execution.id, source_digest=execution.execution_digest, currency=execution.currency, effective_date=date(2026, 9, 16), evidence_digest=canonical_digest({"synthetic-return": True}), delta_components=(EconomicDelta("wage_settlement", Decimal("-100.00")),))
        value = await service.create(session, context=manage, draft=command)
        await session.refresh(execution)
        assert value.source_id == execution.id
        assert execution.execution_digest == original_digest and execution.lifecycle == original_state
