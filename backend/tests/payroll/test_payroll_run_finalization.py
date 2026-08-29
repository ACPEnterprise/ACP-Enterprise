from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.models import BusinessEvent
from app.payroll.contracts import (
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from app.payroll.finalization import GrossReviewDecision, PayrollGrossResultService
from app.payroll.models import EmployeeCompensationAuthorityVersion
from app.payroll.permissions import PayrollPermission
from app.payroll.run_finalization import (
    PayrollPopulationEvidence,
    PayrollRunDisposition,
    PayrollRunMemberInput,
    PayrollRunReviewDecision,
    PayrollRunService,
)
from app.payroll.tax_authority import TaxDeductionAdmissionState
from app.payroll.tax_calculation import ApprovedGrossPayEvidence
from app.payroll.tax_finalization import (
    PayrollTaxDeductionResultService,
    TaxReviewDecision,
)
from app.platform.audit.models import AuditRecord
from app.platform.employees.models import Employee
from app.timekeeping.models import PayrollTimeInputRecord
from tests.payroll.test_gross_pay_calculation import compensation
from tests.payroll.test_gross_pay_finalization import (
    FakeContext,
    candidate,
    seed_candidate_time,
)
from tests.payroll.test_gross_pay_finalization import (
    finalization_database as _finalization_database_fixture,
)
from tests.payroll.test_tax_deduction_calculation import admission, execute

finalization_database = _finalization_database_fixture
NOW = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)


def population(company_id: UUID, pay_period_id: UUID, employees: tuple[UUID, ...]) -> PayrollPopulationEvidence:
    provisional = PayrollPopulationEvidence(company_id, pay_period_id, "synthetic-active-population", "payroll.population.v1", employees, "")
    return replace(provisional, evidence_digest=canonical_digest(provisional.canonical_content()))


def contexts(values: dict[str, object]) -> tuple[Any, Any, Any, Any]:
    assemble = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.RUN_ASSEMBLE})
    read = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.RUN_READ})
    review = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.RUN_REVIEW})
    approve = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.RUN_APPROVE})
    return assemble, read, review, approve


async def approved_tax_result(session: AsyncSession, values: dict[str, object], pay_period_id: UUID | None = None):  # type: ignore[no-untyped-def]
    gross_candidate = candidate(values, pay_period_id=pay_period_id)
    await seed_candidate_time(session, gross_candidate, values["actor_id"])  # type: ignore[arg-type]
    existing_snapshot = await session.scalar(
        select(PayrollTimeInputRecord).where(
            PayrollTimeInputRecord.snapshot_identity
            == gross_candidate.time_snapshot_id
        )
    )
    if existing_snapshot is None:
        session.add(
            PayrollTimeInputRecord(
                id=uuid4(),
                snapshot_identity=gross_candidate.time_snapshot_id,
                snapshot_version="payroll.time-input.v1",
                company_id=gross_candidate.company_id,
                employee_id=gross_candidate.employee_id,
                pay_period_id=gross_candidate.pay_period.pay_period_id,
                approved_revision_ids=[],
                total_approved_minutes=gross_candidate.components[0].payable_minutes,
                snapshot_digest=gross_candidate.time_snapshot_digest,
                created_by_user_id=values["actor_id"],
            )
        )
        await session.commit()
    gross_service = PayrollGrossResultService()
    gross_execute = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.CALCULATION_EXECUTE})
    gross_review = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.CALCULATION_REVIEW})
    gross = await gross_service.persist_candidate(session, context=gross_execute, candidate=gross_candidate)
    await gross_service.initiate_review(session, context=gross_review, result_id=gross.id, reason_code="synthetic")
    await gross_service.decide_review(session, context=gross_review, result_id=gross.id, decision=GrossReviewDecision.ACCEPTED, reason_code="synthetic")
    evidence = ApprovedGrossPayEvidence(gross.id, gross.lifecycle, gross.company_id, gross.employee_id, gross.pay_period_id, gross.calculation_digest, gross.currency, gross.gross_pay_total, gross_candidate)
    admitted = admission(evidence, (), state=TaxDeductionAdmissionState.NOT_APPLICABLE)
    tax_candidate = execute(gross=evidence, admission=admitted)
    tax_service = PayrollTaxDeductionResultService()
    tax_execute = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.TAX_CALCULATION_EXECUTE})
    tax_review = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.TAX_RESULT_REVIEW})
    tax = await tax_service.persist_candidate(session, context=tax_execute, candidate=tax_candidate, admission=admitted)
    await tax_service.initiate_review(session, context=tax_review, result_id=tax.id, reason_code="synthetic")
    await tax_service.decide_review(session, context=tax_review, result_id=tax.id, decision=TaxReviewDecision.ACCEPTED, reason_code="synthetic")
    await session.refresh(tax)
    return tax, admitted


async def add_second_employee(
    session: AsyncSession, values: dict[str, object]
) -> dict[str, object]:
    employee_id = uuid4()
    authority = compensation(values["company_id"], employee_id)  # type: ignore[arg-type]
    session.add(
        Employee(
            id=employee_id,
            company_id=values["company_id"],
            home_branch_id=None,
            employee_number=f"READY-{uuid4().hex[:6]}",
            first_name="Second",
            last_name="Synthetic",
            display_name="Second Synthetic",
            employee_type="employee",
            status="active",
        )
    )
    await session.flush()
    session.add(
        EmployeeCompensationAuthorityVersion(
            id=authority.authority_id,
            company_id=authority.company_id,
            employee_id=employee_id,
            authority_version=authority.authority_version,
            effective_start=authority.effective_start,
            effective_end=authority.effective_end,
            lifecycle="approved",
            definition_version="payroll.compensation-authority.v1",
            compensation_type=authority.compensation_type.value,
            hourly_rate=authority.hourly_rate,
            salary_amount=None,
            salary_frequency=None,
            worker_class_reference=authority.worker_class_reference,
            additional_earning_types=[],
            recurring_components=[],
            decision_evidence_digest=authority.decision_evidence_digest,
            authority_digest=authority.authority_digest,
            supersedes_authority_id=None,
            drafted_by_user_id=values["actor_id"],
            approved_by_user_id=values["reviewer_id"],
            approved_at=NOW,
            retired_by_user_id=None,
            retired_at=None,
            audit_reason="Synthetic Payroll-run qualification",
        )
    )
    await session.commit()
    return {**values, "employee_id": employee_id, "compensation": authority}


@pytest.mark.asyncio
async def test_assembly_totals_replay_review_approval_and_safe_handoffs(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollRunService()
    assemble, read, review, approve = contexts(values)
    async with factory() as session:
        tax, _ = await approved_tax_result(session, values)
        second_values = await add_second_employee(session, values)
        second_tax, _ = await approved_tax_result(session, second_values, tax.pay_period_id)
        evidence = population(values["company_id"], tax.pay_period_id, (values["employee_id"], second_values["employee_id"]))  # type: ignore[arg-type]
        member = PayrollRunMemberInput(values["employee_id"], PayrollRunDisposition.READY, tax_result_id=tax.id)  # type: ignore[arg-type]
        second_member = PayrollRunMemberInput(second_values["employee_id"], PayrollRunDisposition.READY, tax_result_id=second_tax.id)  # type: ignore[arg-type]
        candidate_value = await service.assemble_candidate(session, context=assemble, population=evidence, member_inputs=(member, second_member), currency="USD", assembled_at=NOW)
        assert candidate_value.aggregate_gross == tax.gross_pay + second_tax.gross_pay
        assert candidate_value.aggregate_net_pay == tax.net_pay_candidate + second_tax.net_pay_candidate
        first = await service.persist_candidate(session, context=assemble, candidate=candidate_value)
        replay = await service.persist_candidate(session, context=assemble, candidate=candidate_value)
        assert first.id == replay.id
        await service.initiate_review(session, context=review, run_id=first.id, reason_code="synthetic")
        await service.decide_review(session, context=review, run_id=first.id, decision=PayrollRunReviewDecision.ACCEPTED, reason_code="synthetic")
        await service.approve(session, context=approve, run_id=first.id, reason_code="synthetic")
        payment = await service.approved_handoff(session, context=read, run_id=first.id, purpose="future_payment_release")
        accounting = await service.approved_handoff(session, context=read, run_id=first.id, purpose="future_accounting_posting")
        assert payment.run_digest == accounting.run_digest == first.run_digest
        events = tuple((await session.scalars(select(BusinessEvent).where(BusinessEvent.entity_type == "payroll_run"))).all())
        audits = tuple((await session.scalars(select(AuditRecord).where(AuditRecord.resource_type == "payroll_run"))).all())
        assert events and audits
        assert all("net_pay" not in str(item.payload) and "aggregate" not in str(item.payload) for item in events)
        assert all("net_pay" not in str(item.details) and "aggregate" not in str(item.details) for item in audits)


@pytest.mark.asyncio
async def test_population_completeness_blocked_evidence_and_company_scope(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollRunService()
    assemble, _, _, _ = contexts(values)
    async with factory() as session:
        tax, admitted = await approved_tax_result(session, values)
        blocked_id = uuid4()
        session.add(Employee(id=blocked_id, company_id=values["company_id"], home_branch_id=None, employee_number=f"BLOCK-{uuid4().hex[:6]}", first_name="Blocked", last_name="Synthetic", display_name="Blocked Synthetic", employee_type="employee", status="active"))
        await session.commit()
        blocked = replace(admitted, employee_id=blocked_id, state=TaxDeductionAdmissionState.MISSING, blockers=("synthetic:missing",), admission_digest="")
        blocked = replace(blocked, admission_digest=canonical_digest(blocked.canonical_content()))
        evidence = population(values["company_id"], tax.pay_period_id, (values["employee_id"], blocked_id))  # type: ignore[arg-type]
        ready = PayrollRunMemberInput(values["employee_id"], PayrollRunDisposition.READY, tax_result_id=tax.id)  # type: ignore[arg-type]
        blocked_member = PayrollRunMemberInput(blocked_id, PayrollRunDisposition.BLOCKED, blocked_admission=blocked)
        with pytest.raises(PayrollConflictError, match="incomplete"):
            await service.assemble_candidate(session, context=assemble, population=evidence, member_inputs=(ready,), currency="USD", assembled_at=NOW)
        candidate_value = await service.assemble_candidate(session, context=assemble, population=evidence, member_inputs=(ready, blocked_member), currency="USD", assembled_at=NOW)
        persisted = await service.persist_candidate(session, context=assemble, candidate=candidate_value)
        assert len(candidate_value.members) == 2 and candidate_value.aggregate_net_pay == tax.net_pay_candidate
        other = FakeContext(values["other_company_id"], values["actor_id"], {PayrollPermission.RUN_READ})
        with pytest.raises(PayrollConflictError, match="not found"):
            await service.run(session, context=other, run_id=persisted.id)
        with pytest.raises(PayrollConflictError, match="blocked"):
            bad = PayrollRunMemberInput(blocked_id, PayrollRunDisposition.BLOCKED, blocked_admission=admitted)
            await service.assemble_candidate(session, context=assemble, population=evidence, member_inputs=(ready, bad), currency="USD", assembled_at=NOW)


@pytest.mark.asyncio
async def test_permissions_competing_run_and_append_only_supersession(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = PayrollRunService()
    assemble, _, review, _ = contexts(values)
    async with factory() as session:
        tax, _ = await approved_tax_result(session, values)
        evidence = population(values["company_id"], tax.pay_period_id, (values["employee_id"],))  # type: ignore[arg-type]
        ready = PayrollRunMemberInput(values["employee_id"], PayrollRunDisposition.READY, tax_result_id=tax.id)  # type: ignore[arg-type]
        first_candidate = await service.assemble_candidate(session, context=assemble, population=evidence, member_inputs=(ready,), currency="USD", assembled_at=NOW)
        first = await service.persist_candidate(session, context=assemble, candidate=first_candidate)
        changed_population = replace(evidence, population_identity="synthetic-corrected", evidence_digest="")
        changed_population = replace(changed_population, evidence_digest=canonical_digest(changed_population.canonical_content()))
        competing = await service.assemble_candidate(session, context=assemble, population=changed_population, member_inputs=(ready,), currency="USD", assembled_at=NOW)
        with pytest.raises(PayrollConflictError, match="active"):
            await service.persist_candidate(session, context=assemble, candidate=competing)
        successor = await service.assemble_candidate(session, context=assemble, population=changed_population, member_inputs=(ready,), currency="USD", assembled_at=NOW, supersedes_run_identity=first.run_identity)
        second = await service.persist_candidate(session, context=assemble, candidate=successor)
        await session.refresh(first)
        assert first.lifecycle == "superseded" and second.supersedes_run_id == first.id
        no_permission = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.RUN_ASSEMBLE})
        with pytest.raises(PayrollAuthorizationError):
            await service.initiate_review(session, context=no_permission, run_id=second.id, reason_code="denied")
        await service.initiate_review(session, context=review, run_id=second.id, reason_code="synthetic")
        with pytest.raises(PayrollAuthorizationError):
            await service.approve(session, context=review, run_id=second.id, reason_code="denied")
