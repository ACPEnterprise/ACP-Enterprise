from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.models import BusinessEvent
from app.payroll.contracts import PayrollAuthorizationError, PayrollConflictError
from app.payroll.finalization import GrossReviewDecision, PayrollGrossResultService
from app.payroll.permissions import PayrollPermission
from app.payroll.tax_authority import PayrollInputDomain, TaxDeductionAdmissionState
from app.payroll.tax_calculation import ApprovedGrossPayEvidence, TaxResponsibility
from app.payroll.tax_finalization import (
    PayrollTaxDeductionResultService,
    TaxResultLifecycle,
    TaxReviewDecision,
)
from app.platform.audit.models import AuditRecord
from tests.payroll.test_gross_pay_finalization import (
    FakeContext,
    candidate,
    seed_candidate_time,
)
from tests.payroll.test_gross_pay_finalization import (
    finalization_database as _finalization_database_fixture,
)
from tests.payroll.test_tax_deduction_calculation import (
    admission,
    execute,
    resolution,
    tax_instruction,
)

finalization_database = _finalization_database_fixture


async def approved_gross(
    session: AsyncSession, values: dict[str, object]
) -> ApprovedGrossPayEvidence:
    gross_candidate = candidate(values)
    await seed_candidate_time(session, gross_candidate, values["actor_id"])  # type: ignore[arg-type]
    execute_context: Any = FakeContext(
        values["company_id"], values["actor_id"], {PayrollPermission.CALCULATION_EXECUTE}
    )
    review_context: Any = FakeContext(
        values["company_id"], values["reviewer_id"], {PayrollPermission.CALCULATION_REVIEW}
    )
    service = PayrollGrossResultService()
    persisted = await service.persist_candidate(session, context=execute_context, candidate=gross_candidate)
    await service.initiate_review(session, context=review_context, result_id=persisted.id, reason_code="synthetic")
    await service.decide_review(session, context=review_context, result_id=persisted.id, decision=GrossReviewDecision.ACCEPTED, reason_code="synthetic")
    await session.refresh(persisted)
    return ApprovedGrossPayEvidence(
        persisted_result_id=persisted.id,
        persisted_lifecycle=persisted.lifecycle,
        persisted_company_id=persisted.company_id,
        persisted_employee_id=persisted.employee_id,
        persisted_pay_period_id=persisted.pay_period_id,
        persisted_calculation_digest=persisted.calculation_digest,
        persisted_currency=persisted.currency,
        persisted_gross_pay_total=persisted.gross_pay_total,
        candidate=gross_candidate,
    )


def contexts(values: dict[str, object]) -> tuple[Any, Any, Any]:
    execute_context = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.TAX_CALCULATION_EXECUTE})
    read_context = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.TAX_RESULT_READ})
    review_context = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.TAX_RESULT_REVIEW})
    return execute_context, read_context, review_context


@pytest.mark.asyncio
async def test_persist_replay_review_verification_and_safe_events(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollTaxDeductionResultService()
    execute_context, read_context, review_context = contexts(values)
    async with factory() as session:
        gross = await approved_gross(session, values)
        tax = resolution(gross, PayrollInputDomain.TAX, "synthetic", protected=True)
        accepted = admission(gross, (tax,))
        calculated = execute(gross=gross, admission=accepted, tax_instructions=(tax_instruction(tax, key="synthetic", responsibility=TaxResponsibility.EMPLOYEE_WITHHOLDING, rate="0.10", protected=True),))
        first = await service.persist_candidate(session, context=execute_context, candidate=calculated, admission=accepted)
        replay = await service.persist_candidate(session, context=execute_context, candidate=calculated, admission=accepted)
        assert first.id == replay.id
        await service.initiate_review(session, context=review_context, result_id=first.id, reason_code="synthetic_review")
        await service.decide_review(session, context=review_context, result_id=first.id, decision=TaxReviewDecision.ACCEPTED, reason_code="synthetic_accepted")
        await session.refresh(first)
        assert first.lifecycle == TaxResultLifecycle.APPROVED.value
        assert (await service.result(session, context=read_context, result_id=first.id)).id == first.id
        first.net_pay_candidate += 1
        await session.flush()
        with pytest.raises(Exception, match="reconciliation|digest"):
            await service.result(session, context=read_context, result_id=first.id)
        await session.rollback()
        events = tuple((await session.scalars(select(BusinessEvent).where(BusinessEvent.entity_type == "payroll_tax_deduction_result"))).all())
        audits = tuple((await session.scalars(select(AuditRecord).where(AuditRecord.resource_type == "payroll_tax_deduction_result"))).all())
        assert events and audits
        assert all("net_pay" not in str(item.payload) for item in events)
        assert all("net_pay" not in str(item.details) for item in audits)


@pytest.mark.asyncio
async def test_blocked_not_applicable_authorization_and_company_isolation(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollTaxDeductionResultService()
    execute_context, read_context, _ = contexts(values)
    async with factory() as session:
        gross = await approved_gross(session, values)
        blocked = admission(gross, (), state=TaxDeductionAdmissionState.MISSING)
        not_applicable = admission(gross, (), state=TaxDeductionAdmissionState.NOT_APPLICABLE)
        empty = execute(gross=gross, admission=not_applicable)
        with pytest.raises(PayrollConflictError, match="blocked"):
            await service.persist_candidate(session, context=execute_context, candidate=empty, admission=blocked)
        no_permission: Any = FakeContext(values["company_id"], values["actor_id"], set())
        with pytest.raises(PayrollAuthorizationError):
            await service.persist_candidate(session, context=no_permission, candidate=empty, admission=not_applicable)
        other: Any = FakeContext(values["other_company_id"], values["actor_id"], {PayrollPermission.TAX_CALCULATION_EXECUTE})
        with pytest.raises(PayrollConflictError, match="scope"):
            await service.persist_candidate(session, context=other, candidate=empty, admission=not_applicable)
        persisted = await service.persist_candidate(session, context=execute_context, candidate=empty, admission=not_applicable)
        statuses = await service.period_results(session, context=read_context, pay_period_id=persisted.pay_period_id, blocked_admissions=(blocked,))
        assert {item.status for item in statuses} == {"calculated", "missing"}
        with pytest.raises(PayrollConflictError, match="blocked"):
            await service.period_results(session, context=read_context, pay_period_id=persisted.pay_period_id, blocked_admissions=(not_applicable,))


@pytest.mark.asyncio
async def test_supersession_is_append_only_and_cannot_fork(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollTaxDeductionResultService()
    execute_context, read_context, _ = contexts(values)
    async with factory() as session:
        gross = await approved_gross(session, values)
        accepted = admission(gross, (), state=TaxDeductionAdmissionState.NOT_APPLICABLE)
        first_candidate = execute(gross=gross, admission=accepted)
        first = await service.persist_candidate(session, context=execute_context, candidate=first_candidate, admission=accepted)
        second_candidate = execute(gross=gross, admission=accepted, supersedes_result_id=first_candidate.result_id)
        # A changed provider/input is represented here by a distinct valid candidate timestamp-independent digest input.
        second_candidate = replace(second_candidate, money_version="money.currency-minor-unit-provider-rounding.v2", calculation_digest="")
        from app.payroll.contracts import canonical_digest
        second_candidate = replace(second_candidate, calculation_digest=canonical_digest(second_candidate.canonical_economic_content()))
        second_candidate = replace(second_candidate, result_id=f"tax-deduction-calculation:{second_candidate.calculation_digest}")
        second = await service.persist_candidate(session, context=execute_context, candidate=second_candidate, admission=accepted)
        await session.refresh(first)
        assert first.lifecycle == "superseded" and second.supersedes_result_id == first.id
        history = await service.history(session, context=read_context, employee_id=gross.persisted_employee_id, pay_period_id=gross.persisted_pay_period_id)
        assert len(history) == 2
        fork = replace(second_candidate, supersedes_result_id=first_candidate.result_id, money_version="money.v3", calculation_digest="")
        fork = replace(fork, calculation_digest=canonical_digest(fork.canonical_economic_content()))
        fork = replace(fork, result_id=f"tax-deduction-calculation:{fork.calculation_digest}")
        with pytest.raises(PayrollConflictError, match="lineage"):
            await service.persist_candidate(session, context=execute_context, candidate=fork, admission=accepted)


@pytest.mark.asyncio
async def test_execute_permission_does_not_grant_review(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollTaxDeductionResultService()
    execute_context, _, _ = contexts(values)
    async with factory() as session:
        gross = await approved_gross(session, values)
        accepted = admission(gross, (), state=TaxDeductionAdmissionState.NOT_APPLICABLE)
        value = await service.persist_candidate(session, context=execute_context, candidate=execute(gross=gross, admission=accepted), admission=accepted)
        with pytest.raises(PayrollAuthorizationError):
            await service.initiate_review(session, context=execute_context, result_id=value.id, reason_code="not_allowed")
