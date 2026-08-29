from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customers.models import Customer  # noqa: F401
from app.payroll.contracts import (
    PayrollAuthorizationError,
    PayrollConflictError,
)
from app.payroll.permissions import PayrollPermission
from app.payroll.remittance import (
    DraftRemittanceDestination,
    DraftRemittancePolicy,
    PayrollRemittanceService,
    ProviderState,
    RemittanceAcknowledgement,
    RemittanceClassification,
    ScheduleState,
    SyntheticRemittanceProvider,
)
from app.scheduling.models import Appointment  # noqa: F401
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_release_authority import approved_run

finalization_database = _database


def ctx(values: dict[str, object], permission: str, *, reviewer: bool = False, other: bool = False) -> Any:
    return FakeContext(values["other_company_id"] if other else values["company_id"], values["reviewer_id"] if reviewer else values["actor_id"], {permission})


async def policy_and_destination(session: AsyncSession, values: dict[str, object], classification: RemittanceClassification, *, due_days: int | None = 7, destination: bool = True):  # type: ignore[no-untyped-def]
    service = PayrollRemittanceService()
    policy = await service.create_policy(session, context=ctx(values, PayrollPermission.REMITTANCE_MANAGE), draft=DraftRemittancePolicy(classification, 1, "USD", True, due_days, destination, "liability_settlement", date(2026, 1, 1), None, "a" * 64))
    await service.approve_policy(session, context=ctx(values, PayrollPermission.REMITTANCE_APPROVE, reviewer=True), policy_id=policy.id)
    if not destination:
        return service, policy, None
    target = await service.create_destination(session, context=ctx(values, PayrollPermission.REMITTANCE_MANAGE), draft=DraftRemittanceDestination("synthetic_tax_agency", "TEST", "protected:synthetic-destination", "Agency •••• TEST", date(2026, 1, 1), None))
    await service.approve_destination(session, context=ctx(values, PayrollPermission.REMITTANCE_APPROVE, reviewer=True), destination_id=target.id)
    return service, policy, target


async def ready_obligation(session: AsyncSession, values: dict[str, object], classification: RemittanceClassification = RemittanceClassification.EMPLOYEE_TAX_WITHHOLDING):  # type: ignore[no-untyped-def]
    run, _ = await approved_run(session, values)
    run.aggregate_employee_taxes = Decimal("100.00")
    run.aggregate_employee_deductions = Decimal("50.00")
    run.aggregate_employer_contributions = Decimal("25.00")
    await session.commit()
    service, _, destination = await policy_and_destination(session, values, classification)
    obligation = await service.identify_obligation(session, context=ctx(values, PayrollPermission.REMITTANCE_MANAGE), payroll_run_id=run.id, classification=classification, destination_id=destination.id)
    return service, run, obligation


@pytest.mark.asyncio
async def test_complete_remittance_partial_settlement_return_and_accounting_handoff(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        service, run, obligation = await ready_obligation(session, values)
        replay = await service.identify_obligation(session, context=ctx(values, PayrollPermission.REMITTANCE_MANAGE), payroll_run_id=run.id, classification=RemittanceClassification.EMPLOYEE_TAX_WITHHOLDING, destination_id=obligation.destination_id)
        assert replay.id == obligation.id and obligation.amount == Decimal("100.00")
        review = ctx(values, PayrollPermission.REMITTANCE_REVIEW, reviewer=True)
        await service.review(session, context=review, obligation_id=obligation.id, decision="initiated", reason_code="synthetic")
        await service.review(session, context=review, obligation_id=obligation.id, decision="accepted", reason_code="synthetic")
        await service.approve(session, context=ctx(values, PayrollPermission.REMITTANCE_APPROVE, reviewer=True), obligation_id=obligation.id, reason_code="synthetic")
        instruction = await service.prepare_instruction(session, context=ctx(values, PayrollPermission.REMITTANCE_EXECUTE), obligation_id=obligation.id, provider_identity=SyntheticRemittanceProvider.identity, provider_version=SyntheticRemittanceProvider.version, idempotency_identity="synthetic-remittance-1")
        assert instruction.amount == obligation.amount
        provider = SyntheticRemittanceProvider(environment="test")
        await service.submit(session, context=ctx(values, PayrollPermission.REMITTANCE_EXECUTE), instruction_id=instruction.id, provider=provider)
        assert provider.calls == 1
        await service.submit(session, context=ctx(values, PayrollPermission.REMITTANCE_EXECUTE), instruction_id=instruction.id, provider=provider)
        assert provider.calls == 1
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        await service.record_settlement(session, context=ctx(values, PayrollPermission.REMITTANCE_RECONCILE), instruction_id=instruction.id, amount=Decimal("40.00"), provider_safe_reference="synthetic-partial", occurred_at=now)
        partial = await service.reconcile(session, context=ctx(values, PayrollPermission.REMITTANCE_READ), obligation_id=obligation.id)
        assert partial.settled == Decimal("40.00") and partial.outstanding == Decimal("60.00") and partial.disposition == "partially_settled"
        await service.record_settlement(session, context=ctx(values, PayrollPermission.REMITTANCE_RECONCILE), instruction_id=instruction.id, amount=Decimal("60.00"), provider_safe_reference="synthetic-final", occurred_at=now)
        handoff = await service.accounting_handoff(session, context=ctx(values, PayrollPermission.REMITTANCE_READ), obligation_id=obligation.id)
        assert handoff.settled_amount == Decimal("100.00") and not handoff.expense_recognition and handoff.recognition_event == "tax_remittance"
        returned = await service.record_return(session, context=ctx(values, PayrollPermission.REMITTANCE_RECONCILE), instruction_id=instruction.id, amount=Decimal("10.00"), provider_safe_reference="synthetic-return", occurred_at=now)
        assert returned.evidence_type == "return"
        reconciliation = await service.reconcile(session, context=ctx(values, PayrollPermission.REMITTANCE_READ), obligation_id=obligation.id)
        assert reconciliation.settled == Decimal("90.00") and reconciliation.outstanding == Decimal("10.00")


@pytest.mark.asyncio
async def test_blocked_due_date_destination_and_source_admission(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        run.aggregate_employee_deductions = Decimal("20.00")
        await session.commit()
        service, _, _ = await policy_and_destination(session, values, RemittanceClassification.EMPLOYEE_DEDUCTION, due_days=None, destination=True)
        obligation = await service.identify_obligation(session, context=ctx(values, PayrollPermission.REMITTANCE_MANAGE), payroll_run_id=run.id, classification=RemittanceClassification.EMPLOYEE_DEDUCTION, destination_id=None)
        assert obligation.lifecycle == "blocked"
        assert await service.schedule_state(session, context=ctx(values, PayrollPermission.REMITTANCE_READ), obligation_id=obligation.id, as_of=date(2026, 9, 20)) is ScheduleState.BLOCKED
        run.lifecycle = "assembled"; await session.commit()
        with pytest.raises(PayrollConflictError, match="approved"):
            await service.identify_obligation(session, context=ctx(values, PayrollPermission.REMITTANCE_MANAGE), payroll_run_id=run.id, classification=RemittanceClassification.EMPLOYER_PAYROLL_TAX, destination_id=None)


@pytest.mark.asyncio
async def test_distinct_liabilities_sod_isolation_uncertain_and_contradictory_ack(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        service, _, obligation = await ready_obligation(session, values, RemittanceClassification.EMPLOYER_PAYROLL_TAX)
        with pytest.raises(PayrollAuthorizationError):
            await service.review(session, context=ctx(values, PayrollPermission.REMITTANCE_MANAGE), obligation_id=obligation.id, decision="initiated", reason_code="no")
        assert await service.obligations(session, context=ctx(values, PayrollPermission.REMITTANCE_READ, other=True)) == ()
        review = ctx(values, PayrollPermission.REMITTANCE_REVIEW, reviewer=True)
        await service.review(session, context=review, obligation_id=obligation.id, decision="initiated", reason_code="synthetic")
        await service.review(session, context=review, obligation_id=obligation.id, decision="accepted", reason_code="synthetic")
        await service.approve(session, context=ctx(values, PayrollPermission.REMITTANCE_APPROVE, reviewer=True), obligation_id=obligation.id, reason_code="synthetic")
        instruction = await service.prepare_instruction(session, context=ctx(values, PayrollPermission.REMITTANCE_EXECUTE), obligation_id=obligation.id, provider_identity=SyntheticRemittanceProvider.identity, provider_version=SyntheticRemittanceProvider.version, idempotency_identity="uncertain-1")
        uncertain = SyntheticRemittanceProvider(environment="test", state=ProviderState.UNCERTAIN)
        await service.submit(session, context=ctx(values, PayrollPermission.REMITTANCE_EXECUTE), instruction_id=instruction.id, provider=uncertain)
        with pytest.raises(PayrollConflictError, match="uncertain"):
            await service.submit(session, context=ctx(values, PayrollPermission.REMITTANCE_EXECUTE), instruction_id=instruction.id, provider=uncertain)
        bad = RemittanceAcknowledgement(ProviderState.ACKNOWLEDGED, "different", "b" * 64, "c" * 64, datetime.now(timezone.utc))
        with pytest.raises(PayrollConflictError, match="contradictory"):
            await service.record_acknowledgement(session, context=ctx(values, PayrollPermission.REMITTANCE_EXECUTE), instruction_id=instruction.id, acknowledgement=bad)
        with pytest.raises(PayrollConflictError, match="test-only"):
            SyntheticRemittanceProvider(environment="production")
