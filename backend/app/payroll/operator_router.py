"""Authenticated operator composition over the existing Payroll authorities.

This router deliberately does not calculate, transmit, or post Payroll. It
exposes the governed run lifecycle only when prerequisite evidence exists.
"""
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.payroll.calculation import PayrollGrossCalculationEngine
from app.payroll.calculation_authority import (
    build_federal_authority_inputs,
    configured_input_cipher,
)
from app.payroll.calculation_inputs import resolve_tax_deduction_requirements
from app.payroll.contracts import PayrollConflictError, canonical_digest
from app.payroll.finalization import GrossReviewDecision, PayrollGrossResultService
from app.payroll.models import (
    PayrollCalculationInputSnapshotRecord,
    PayrollGrossCalculationResultRecord,
    PayrollInputAuthorityVersion,
    PayrollPaperCheckEvidenceRecord,
    PayrollPaymentDestinationVersion,
    PayrollProtectedInputEnvelope,
    PayrollRunCloseRecord,
    PayrollRunMemberRecord,
    PayrollRunRecord,
    PayrollTaxDeductionResultRecord,
)
from app.payroll.operations import PayrollOperationsService
from app.payroll.payment_release import (
    DraftPaymentDestination,
    PaymentMethod,
    PaymentReleaseReviewDecision,
    PayrollPaymentReleaseService,
)
from app.payroll.permissions import PayrollPermission
from app.payroll.run_finalization import (
    PayrollPopulationEvidence,
    PayrollRunDisposition,
    PayrollRunMemberInput,
    PayrollRunReviewDecision,
    PayrollRunService,
)
from app.payroll.service import PayrollAuthorityService
from app.payroll.tax_authority import (
    AuthorityRequirement,
    PayrollInputAuthorityService,
    PayrollInputDomain,
)
from app.payroll.tax_calculation import (
    ApprovedGrossPayEvidence,
    PayrollTaxDeductionCalculationEngine,
    ProviderEnvironment,
)
from app.payroll.tax_finalization import PayrollTaxDeductionResultService
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.employees.models import Employee
from app.platform.idempotency.models import MutationReceipt
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission
from app.timekeeping.contracts import seal_payroll_time_input
from app.timekeeping.models import PayPeriod, PayrollTimeInputRecord
from app.timekeeping.service import WorkdayTimeService

router = APIRouter(prefix="/api/v1/payroll/operator", tags=["Payroll Operator"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.REPORTING_READ))]
Assemble = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_ASSEMBLE))]
Review = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_REVIEW))]
Approve = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_APPROVE))]
Calculate = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.CALCULATION_EXECUTE))]
PaymentRead = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.PAYMENT_RELEASE_READ))]
PaymentManage = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.PAYMENT_INSTRUCTION_MANAGE))]
PaymentAssemble = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.PAYMENT_RELEASE_ASSEMBLE))]
PaymentReview = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.PAYMENT_RELEASE_REVIEW))]
PaymentApprove = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.PAYMENT_RELEASE_APPROVE))]


class RunMemberInput(BaseModel):
    employee_id: UUID
    tax_result_id: UUID | None = None
    disposition: PayrollRunDisposition = PayrollRunDisposition.READY


class AssembleInput(BaseModel):
    pay_period_id: UUID
    employee_ids: list[UUID] = Field(min_length=1)
    members: list[RunMemberInput] = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class ReviewInput(BaseModel):
    reason_code: str = Field(min_length=1, max_length=120)
    safe_note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(default="", min_length=0, max_length=160)


class CalculateInput(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    expected_run_digest: str | None = Field(default=None, min_length=64, max_length=64)


class PaperCheckIssueInput(BaseModel):
    employee_id: UUID
    check_number: str = Field(min_length=1, max_length=80)
    issue_date: date
    idempotency_key: str = Field(min_length=1, max_length=255)


class PaperCheckVoidInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=255)


class PaperCheckReissueInput(PaperCheckIssueInput):
    original_check_id: UUID


class PaperCheckDestinationInput(BaseModel):
    employee_id: UUID
    check_reference: str = Field(min_length=1, max_length=120)
    masked_display: str = Field(min_length=1, max_length=120)
    effective_start: date
    effective_end: date | None = None
    audit_reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=255)


class ReviewDecisionInput(ReviewInput):
    decision: str = Field(pattern="^(accepted|rejected)$")


def _run_blockers(run: PayrollRunRecord, members: tuple[PayrollRunMemberRecord, ...]) -> list[str]:
    blockers: list[str] = []
    if run.lifecycle not in {"assembled", "under_review", "reviewed", "approved"}:
        blockers.append("RUN_NOT_CALCULABLE")
    if not members:
        blockers.append("NO_ELIGIBLE_REAL_EMPLOYEES")
    for member in members:
        if member.disposition == "ready" and (member.gross_result_id is None or member.tax_result_id is None):
            blockers.append(f"MISSING_CALCULATION_RESULT:{member.employee_id}")
        blockers.extend(member.blocker_codes or ())
    return sorted(set(blockers))


@router.get("/workflow")
async def workflow(context: Read, session: Session) -> dict[str, object]:
    summary = await PayrollOperationsService().summary(session, context=context)
    blockers: list[str] = []
    if not summary.run_counts:
        blockers.append("NO_PAYROLL_RUN")
    if not summary.history_ready:
        blockers.append("MISSING_PRIOR_PAYROLL_COVERAGE")
    return {
        "contract_version": "payroll.operator-workflow.v1",
        "run_counts": summary.run_counts,
        "member_dispositions": summary.member_dispositions,
        "payment_counts": summary.payment_counts,
        "approved_net": str(summary.aggregate_approved_net),
        "blockers": blockers,
        "boundaries": ["paper_check_evidence_only", "no_ach", "no_tax_filing", "no_accounting_posting"],
    }


@router.post("/runs/assemble")
async def assemble_run(payload: AssembleInput, context: Assemble, session: Session) -> dict[str, object]:
    ids = tuple(payload.employee_ids)
    members = tuple(payload.members)
    if len(set(ids)) != len(ids) or {item.employee_id for item in members} != set(ids):
        raise HTTPException(422, "Payroll population and member evidence must match exactly.")
    if any(item.disposition is PayrollRunDisposition.READY and item.tax_result_id is None for item in members):
        raise HTTPException(422, "Approved tax results are required before a Payroll run can be assembled.")
    population_content = {
        "company_id": str(context.company.id),
        "pay_period_id": str(payload.pay_period_id),
        "population_identity": "payroll-operator-population-v1",
        "definition_version": "payroll.operator-workflow.v1",
        "employee_ids": tuple(sorted(str(item) for item in ids)),
    }
    population = PayrollPopulationEvidence(
        company_id=context.company.id,
        pay_period_id=payload.pay_period_id,
        population_identity="payroll-operator-population-v1",
        definition_version="payroll.operator-workflow.v1",
        employee_ids=ids,
        evidence_digest=canonical_digest(population_content),
    )
    try:
        service = PayrollRunService()
        candidate = await service.assemble_candidate(
            session,
            context=context,
            population=population,
            member_inputs=tuple(PayrollRunMemberInput(employee_id=item.employee_id, disposition=item.disposition, tax_result_id=item.tax_result_id) for item in members),
            currency=payload.currency,
            assembled_at=datetime.now(timezone.utc),
        )
        value = await service.persist_candidate(session, context=context, candidate=candidate)
        return {"run_id": value.id, "lifecycle": value.lifecycle, "run_digest": value.run_digest}
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/runs/{run_id}/review")
async def review_run(run_id: UUID, payload: ReviewInput, context: Review, session: Session) -> dict[str, object]:
    value = await PayrollRunService().initiate_review(session, context=context, run_id=run_id, reason_code=payload.reason_code, safe_note=payload.safe_note)
    return {"run_id": value.run_id, "decision": value.decision, "review_digest": value.review_digest}


@router.post("/runs/{run_id}/review/decision")
async def decide_run_review(run_id: UUID, payload: ReviewDecisionInput, context: Review, session: Session) -> dict[str, object]:
    try:
        decision = PayrollRunReviewDecision(payload.decision)
        value = await PayrollRunService().decide_review(
            session,
            context=context,
            run_id=run_id,
            decision=decision,
            reason_code=payload.reason_code,
            safe_note=payload.safe_note,
        )
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"run_id": value.run_id, "decision": value.decision, "review_digest": value.review_digest}


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: UUID, payload: ReviewInput, context: Approve, session: Session) -> dict[str, object]:
    value = await PayrollRunService().approve(session, context=context, run_id=run_id, reason_code=payload.reason_code, safe_note=payload.safe_note)
    return {"run_id": value.run_id, "decision": value.decision, "review_digest": value.review_digest}


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID, context: Read, session: Session) -> dict[str, object]:
    """Return a safe operator projection of one Company-scoped Payroll run.

    ``approved`` is the existing immutable Payroll authority.  This projection
    deliberately labels it as such instead of inventing a close/GL-posted
    state; Accounting, tax filing, and payment execution remain separate
    governed boundaries.
    """
    service = PayrollRunService()
    try:
        run = await service.run(session, context=context, run_id=run_id)
    except PayrollConflictError as error:
        raise HTTPException(404, str(error)) from error
    members = tuple(
        (
            await session.scalars(
                select(PayrollRunMemberRecord)
                .where(
                    PayrollRunMemberRecord.company_id == context.company.id,
                    PayrollRunMemberRecord.run_id == run.id,
                )
                .order_by(PayrollRunMemberRecord.employee_id)
            )
        ).all()
    )
    return {
        "run_id": run.id,
        "pay_period_id": run.pay_period_id,
        "lifecycle": run.lifecycle,
        "review_state": run.review_state,
        "immutable_payroll_authority": run.lifecycle == "approved",
        "accounting_posted": False,
        "payment_execution": "not_performed",
        "tax_filing": "not_performed",
        "run_digest": run.run_digest,
        "currency": run.currency,
        "aggregate_gross": str(run.aggregate_gross),
        "aggregate_employee_taxes": str(run.aggregate_employee_taxes),
        "aggregate_employee_deductions": str(run.aggregate_employee_deductions),
        "aggregate_net_pay": str(run.aggregate_net_pay),
        "members": [
            {
                "employee_id": item.employee_id,
                "disposition": item.disposition,
                "gross_result_id": item.gross_result_id,
                "gross_result_digest": item.gross_result_digest,
                "tax_result_id": item.tax_result_id,
                "tax_result_digest": item.tax_result_digest,
                "blocker_codes": item.blocker_codes,
            }
            for item in members
        ],
    }


@router.post("/runs/{run_id}/calculate")
async def calculate_run(run_id: UUID, payload: CalculateInput, context: Calculate, session: Session) -> dict[str, object]:
    """Compose the existing calculation authorities for operator use.

    Calculation engines persist immutable gross/tax results before run assembly;
    this route never fabricates inputs or recalculates a closed run. It returns
    blocker evidence until those governed results exist, and otherwise exposes
    the exact result references bound to the run.
    """
    run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == run_id))
    if run is None:
        raise HTTPException(404, "Payroll run was not found")
    if payload.expected_run_digest is not None and payload.expected_run_digest != run.run_digest:
        raise HTTPException(409, "Payroll run version is stale")
    if await session.scalar(select(PayrollRunCloseRecord.id).where(PayrollRunCloseRecord.company_id == context.company.id, PayrollRunCloseRecord.run_id == run.id)) is not None:
        raise HTTPException(409, "closed Payroll authority cannot be recalculated")
    request_digest = canonical_digest({"run_id": str(run_id), "operation": "calculate"})
    operation = "payroll.run.calculate"
    replay = await session.scalar(select(MutationReceipt).where(MutationReceipt.company_id == context.company.id, MutationReceipt.operation == operation, MutationReceipt.idempotency_key == payload.idempotency_key))
    if replay is not None:
        if replay.request_digest != request_digest or replay.result_id != run.id:
            raise HTTPException(409, "calculation idempotency identity conflicts with the original request")
        return {"run_id": run.id, "status": "calculated", "calculation": "existing_governed_results", "run_digest": run.run_digest, "replayed": True}
    members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.company_id == context.company.id, PayrollRunMemberRecord.run_id == run.id))).all())
    blockers = _run_blockers(run, members)
    for member in members:
        resolution = await resolve_tax_deduction_requirements(session, company_id=context.company.id, employee_id=member.employee_id, as_of_date=run.assembled_at.date())
        blockers.extend(resolution.blockers)
    if blockers:
        raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": blockers})
    # A pending-calculation member has no output authority yet.  Resolve the
    # canonical policy/compensation inputs and execute the governed engines;
    # existing result references are only used for replay.
    if any(item.gross_result_id is None for item in members):
        period = await session.scalar(select(PayPeriod).where(PayPeriod.company_id == context.company.id, PayPeriod.id == run.pay_period_id))
        if period is None:
            raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": ["PAY_PERIOD_MISSING"]})
        authority = PayrollAuthorityService()
        gross_service = PayrollGrossResultService()
        tax_service = PayrollTaxDeductionResultService()
        gross_engine = PayrollGrossCalculationEngine()
        tax_engine = PayrollTaxDeductionCalculationEngine(runtime_environment=ProviderEnvironment.PRODUCTION)
        for member in members:
            if member.gross_result_id is not None:
                continue
            policy = await authority.resolve_policy(session, company_id=context.company.id, as_of_date=period.period_start)
            compensation = await authority.resolve_period_compensation(session, company_id=context.company.id, employee_id=member.employee_id, period_start=period.period_start, period_end=period.period_end)
            if policy is None or compensation is None:
                raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": [f"MISSING_COMPENSATION_OR_POLICY:{member.employee_id}"]})
            time_input = None
            if compensation.compensation_type.value == "hourly":
                time_record = await session.scalar(select(PayrollTimeInputRecord).where(PayrollTimeInputRecord.company_id == context.company.id, PayrollTimeInputRecord.employee_id == member.employee_id, PayrollTimeInputRecord.pay_period_id == period.id).order_by(PayrollTimeInputRecord.created_at.desc()))
                resolver = getattr(WorkdayTimeService(), "resolve_payroll_time_input_facts", None)
                if time_record is None or resolver is None:
                    raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": [f"APPROVED_TIME_RESOLVER_REQUIRED:{member.employee_id}"]})
                facts = await resolver(session, context=context, payroll_input=time_record)
                time_input = seal_payroll_time_input(company_id=context.company.id, employee_id=member.employee_id, pay_period_id=period.id, period_start=period.period_start, period_end=period.period_end, approved_entries=tuple(facts))
            admission = await authority.evaluate_admission(session, context=context, identity_resolved=True, policy=policy, compensation=compensation, time_input=time_input, pay_period_schedule_definition_id=period.schedule_definition_id, pay_period_schedule_version=int(period.schedule_version))
            from app.payroll.calculation_adapter import build_gross_inputs
            inputs = build_gross_inputs(company_id=context.company.id, employee_id=member.employee_id, pay_period_id=period.id, period_start=period.period_start, period_end=period.period_end, schedule_definition_id=period.schedule_definition_id, schedule_version=int(period.schedule_version), admission=admission, policy=policy, compensation=compensation)
            candidate = gross_engine.calculate(actor_permissions=context.permission_codes, company_id=inputs.company_id, employee_id=inputs.employee_id, period=inputs.period, admission=inputs.admission, policy=inputs.policy, compensation=inputs.compensation, time_input=time_input, currency=run.currency, calculated_at=datetime.now(timezone.utc))
            persisted_gross = await gross_service.persist_candidate(session, context=context, candidate=candidate)
            # The tax engine consumes an approved gross evidence contract.  Use
            # the existing governed review transition rather than fabricating a
            # second gross result authority.
            await gross_service.initiate_review(session, context=context, result_id=persisted_gross.id, reason_code="operator_calculate")
            await gross_service.decide_review(session, context=context, result_id=persisted_gross.id, decision=GrossReviewDecision.ACCEPTED, reason_code="operator_calculate")
            requirements = (AuthorityRequirement(PayrollInputDomain.TAX, "federal_income_tax", member.employee_id), AuthorityRequirement(PayrollInputDomain.TAX, "social_security_employee", member.employee_id), AuthorityRequirement(PayrollInputDomain.TAX, "medicare_employee", member.employee_id))
            tax_admission = await PayrollInputAuthorityService(cipher=configured_input_cipher()).evaluate_admission(session, context=context, gross_result_id=persisted_gross.id, as_of_date=period.period_start, requirements=requirements)
            if tax_admission.state.value not in {"ready", "not_applicable"}:
                raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": list(tax_admission.blockers)})
            resolutions = tuple(item for item in tax_admission.resolutions if item.authority_id is not None)
            authority_rows = tuple((await session.scalars(select(PayrollInputAuthorityVersion).where(PayrollInputAuthorityVersion.company_id == context.company.id, PayrollInputAuthorityVersion.id.in_([item.authority_id for item in resolutions])))).all())
            envelope_ids = [item.protected_envelope_id for item in authority_rows if item.protected_envelope_id is not None]
            envelope_rows = tuple((await session.scalars(select(PayrollProtectedInputEnvelope).where(PayrollProtectedInputEnvelope.company_id == context.company.id, PayrollProtectedInputEnvelope.id.in_(envelope_ids)))).all()) if envelope_ids else ()
            envelopes = {item.id: item for item in envelope_rows}
            federal = build_federal_authority_inputs(company_id=context.company.id, employee_id=member.employee_id, effective_on=period.period_start, pay_frequency=str(policy.definition.pay_frequency), authorities=authority_rows, envelopes=envelopes, cipher=configured_input_cipher())
            evidence = ApprovedGrossPayEvidence(persisted_result_id=persisted_gross.id, persisted_lifecycle="approved", persisted_company_id=persisted_gross.company_id, persisted_employee_id=persisted_gross.employee_id, persisted_pay_period_id=persisted_gross.pay_period_id, persisted_calculation_digest=persisted_gross.calculation_digest, persisted_currency=persisted_gross.currency, persisted_gross_pay_total=persisted_gross.gross_pay_total, candidate=candidate)
            tax_candidate = tax_engine.calculate(actor_permissions=context.permission_codes, gross=evidence, admission=tax_admission, tax_instructions=federal.tax_instructions, deduction_instructions=federal.deduction_instructions, calculated_at=datetime.now(timezone.utc))
            persisted_tax = await tax_service.persist_candidate(session, context=context, candidate=tax_candidate, admission=tax_admission)
            member.gross_result_id = persisted_gross.id
            member.gross_result_digest = persisted_gross.calculation_digest
            member.tax_result_id = persisted_tax.id
            member.tax_result_digest = persisted_tax.calculation_digest
            member.disposition = "ready"
            await session.commit()
        members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.company_id == context.company.id, PayrollRunMemberRecord.run_id == run.id))).all())

    gross_ids = [item.gross_result_id for item in members if item.gross_result_id is not None]
    gross_rows = tuple((await session.scalars(select(PayrollGrossCalculationResultRecord).where(PayrollGrossCalculationResultRecord.company_id == context.company.id, PayrollGrossCalculationResultRecord.id.in_(gross_ids)))).all()) if gross_ids else ()
    policy_refs = [{"policy_id": str(item.policy_id), "policy_digest": item.policy_digest} for item in gross_rows]
    if not policy_refs:
        raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": ["CALCULATION_ENGINE_INPUT_ADAPTER_REQUIRED"]})
    if len({(item["policy_id"], item["policy_digest"]) for item in policy_refs}) != 1:
        raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": ["PAYROLL_POLICY_AUTHORITY_MISSING_OR_AMBIGUOUS"]})
    employee_bindings = [{"employee_id": str(item.employee_id), "membership_digest": item.membership_digest, "gross_result_id": str(item.gross_result_id), "gross_result_digest": item.gross_result_digest, "tax_result_id": str(item.tax_result_id), "tax_result_digest": item.tax_result_digest} for item in members]
    authority_refs = [{"employee_id": str(item.employee_id), "tax_result_id": str(item.tax_result_id), "tax_result_digest": item.tax_result_digest} for item in members]
    snapshot_content = {"run_id": str(run.id), "run_digest": run.run_digest, "pay_period_id": str(run.pay_period_id), "employee_bindings": employee_bindings, "policy_reference": policy_refs[0], "authority_references": authority_refs}
    snapshot_digest = canonical_digest(snapshot_content)
    existing_snapshot = await session.scalar(select(PayrollCalculationInputSnapshotRecord).where(PayrollCalculationInputSnapshotRecord.company_id == context.company.id, PayrollCalculationInputSnapshotRecord.input_digest == snapshot_digest))
    if existing_snapshot is None:
        latest = await session.scalar(select(PayrollCalculationInputSnapshotRecord.snapshot_version).where(PayrollCalculationInputSnapshotRecord.company_id == context.company.id, PayrollCalculationInputSnapshotRecord.run_id == run.id).order_by(PayrollCalculationInputSnapshotRecord.snapshot_version.desc()).limit(1))
        session.add(PayrollCalculationInputSnapshotRecord(company_id=context.company.id, run_id=run.id, snapshot_version=(latest or 0) + 1, run_digest=run.run_digest, pay_period_id=run.pay_period_id, employee_bindings=employee_bindings, policy_reference=policy_refs[0], authority_references=authority_refs, input_digest=snapshot_digest, replay_identity=payload.idempotency_key, created_by_user_id=context.user.id))
    session.add(MutationReceipt(company_id=context.company.id, actor_user_id=context.user.id, operation=operation, idempotency_key=payload.idempotency_key, request_digest=request_digest, state="completed", result_type="payroll_run_calculation", result_id=run.id, response_status=200, retention_class="financial_audit", completed_at=datetime.now(timezone.utc)))
    AuditService.stage(session, AuditEntry(action="payroll.run.calculated", resource_type="payroll_run", actor_user_id=context.user.id, company_id=context.company.id, resource_id=run.id, reason_code="operator_calculate", details={"run_digest": run.run_digest, "replay_identity": payload.idempotency_key}))
    await session.commit()
    return {
        "run_id": run.id,
        "status": "calculated",
        "calculation": "existing_governed_results",
        "members": [{"employee_id": item.employee_id, "gross_result_id": item.gross_result_id, "tax_result_id": item.tax_result_id} for item in members],
        "run_digest": run.run_digest,
        "replay": "same immutable result references",
        "replayed": False,
    }


@router.post("/runs/{run_id}/close")
async def close_run(run_id: UUID, payload: ReviewInput, context: Approve, session: Session) -> dict[str, object]:
    """Persist an append-only close receipt for the approved terminal authority."""
    try:
        handoff = await PayrollRunService().approved_handoff(session, context=context, run_id=run_id, purpose="future_payment_release")
    except PayrollConflictError as error:
        raise HTTPException(409, str(error)) from error
    if not payload.idempotency_key:
        raise HTTPException(422, "idempotency_key is required to close Payroll")
    replay_identity = f"payroll-close:{payload.idempotency_key}"
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"payroll-close:{context.company.id}:{run_id}"})
    existing = await session.scalar(select(PayrollRunCloseRecord).where(PayrollRunCloseRecord.company_id == context.company.id, PayrollRunCloseRecord.replay_identity == replay_identity).with_for_update())
    if existing is not None:
        if existing.run_id != run_id or existing.close_reason != payload.reason_code:
            raise HTTPException(409, "close idempotency identity conflicts with the original request")
        return {"run_id": existing.run_id, "status": "closed_payroll_authority", "terminal_lifecycle": "approved", "close_receipt": existing.close_digest, "replayed": True, "accounting_posted": False, "payment_execution": "not_performed", "tax_filing": "not_performed"}
    now = datetime.now(timezone.utc)
    close_digest = canonical_digest({"run_id": str(run_id), "prior_run_digest": handoff.run_digest, "replay_identity": replay_identity, "reason": payload.reason_code})
    value = PayrollRunCloseRecord(company_id=context.company.id, run_id=run_id, prior_run_digest=handoff.run_digest, close_state="closed", close_version=1, closed_by_user_id=context.user.id, closed_at=now, close_reason=payload.reason_code, register_digest=handoff.run_digest, replay_identity=replay_identity, close_digest=close_digest)
    session.add(value)
    AuditService.stage(session, AuditEntry(action="payroll.run.closed", resource_type="payroll_run_close", actor_user_id=context.user.id, company_id=context.company.id, resource_id=value.id, reason_code=payload.reason_code, details={"run_id": str(run_id), "run_digest": handoff.run_digest, "replay_identity": replay_identity}))
    BusinessEventService.stage(session, BusinessEventCreate(event_type=EventType.PAYROLL_RUN_CLOSED, entity_type="payroll_run", entity_id=run_id, company_id=context.company.id, user_id=context.user.id, payload={"version": "1", "run_digest": handoff.run_digest, "close_digest": close_digest, "terminal_lifecycle": "approved"}))
    await session.commit()
    return {
        "run_id": handoff.run_id,
        "status": "closed_payroll_authority",
        "terminal_lifecycle": "approved",
        "close_receipt": close_digest,
        "close_reason": payload.reason_code,
        "replayed": False,
        "accounting_posted": False,
        "payment_execution": "not_performed",
        "tax_filing": "not_performed",
    }


@router.post("/paper-check-destinations")
async def create_paper_check_destination(payload: PaperCheckDestinationInput, context: PaymentManage, session: Session) -> dict[str, object]:
    employee = await session.scalar(
        select(Employee).where(Employee.company_id == context.company.id, Employee.id == payload.employee_id, Employee.status == "active")
    )
    if employee is None:
        raise HTTPException(404, "active Employee was not found in this Company")
    request_digest = canonical_digest({
        "employee_id": str(payload.employee_id),
        "check_reference": payload.check_reference,
        "masked_display": payload.masked_display,
        "effective_start": payload.effective_start.isoformat(),
        "effective_end": payload.effective_end.isoformat() if payload.effective_end else None,
        "audit_reason": payload.audit_reason,
    })
    operation = "payroll.paper_check_destination.create"
    replay = await session.scalar(select(MutationReceipt).where(
        MutationReceipt.company_id == context.company.id,
        MutationReceipt.operation == operation,
        MutationReceipt.idempotency_key == payload.idempotency_key,
    ))
    if replay is not None:
        if replay.request_digest != request_digest:
            raise HTTPException(409, "paper-check destination idempotency identity conflicts with the original request")
        if replay.result_id is None:
            raise HTTPException(409, "paper-check destination replay is not recoverable")
        existing = await session.scalar(select(PayrollPaymentDestinationVersion).where(PayrollPaymentDestinationVersion.company_id == context.company.id, PayrollPaymentDestinationVersion.id == replay.result_id))
        if existing is None:
            raise HTTPException(409, "paper-check destination replay evidence is unavailable")
        return {"destination_id": existing.id, "employee_id": existing.employee_id, "method": existing.method_type, "lifecycle": existing.lifecycle, "masked_display": existing.masked_display, "replayed": True}
    try:
        value = await PayrollPaymentReleaseService().create_destination(
            session,
            context=context,
            draft=DraftPaymentDestination(
                employee_id=payload.employee_id,
                destination_version=1,
                method=PaymentMethod.PAPER_CHECK,
                destination_reference=payload.check_reference,
                masked_display=payload.masked_display,
                verification_evidence_digest=canonical_digest({"method": "paper_check", "employee_id": str(payload.employee_id), "reference": payload.check_reference}),
                effective_start=payload.effective_start,
                effective_end=payload.effective_end,
                protected_payload=None,
                audit_reason=payload.audit_reason,
            ),
        )
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    session.add(MutationReceipt(company_id=context.company.id, actor_user_id=context.user.id, operation=operation, idempotency_key=payload.idempotency_key, request_digest=request_digest, state="completed", result_type="payroll_payment_destination", result_id=value.id, response_status=200, retention_class="financial_audit", completed_at=datetime.now(timezone.utc)))
    await session.commit()
    return {"destination_id": value.id, "employee_id": value.employee_id, "method": value.method_type, "lifecycle": value.lifecycle, "masked_display": value.masked_display, "replayed": False}


@router.post("/paper-check-destinations/{destination_id}/approve")
async def approve_paper_check_destination(destination_id: UUID, context: PaymentManage, session: Session) -> dict[str, object]:
    try:
        value = await PayrollPaymentReleaseService().approve_destination(session, context=context, destination_id=destination_id)
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"destination_id": value.id, "employee_id": value.employee_id, "method": value.method_type, "lifecycle": value.lifecycle, "masked_display": value.masked_display}


@router.post("/runs/{run_id}/paper-checks")
async def issue_paper_check(run_id: UUID, payload: PaperCheckIssueInput, context: PaymentManage, session: Session) -> dict[str, object]:
    run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == run_id, PayrollRunRecord.lifecycle == "approved"))
    if run is None:
        raise HTTPException(409, "approved Payroll authority is required before issuing paper-check evidence")
    member = await session.scalar(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.company_id == context.company.id, PayrollRunMemberRecord.run_id == run_id, PayrollRunMemberRecord.employee_id == payload.employee_id, PayrollRunMemberRecord.disposition == "ready"))
    if member is None or member.tax_result_id is None:
        raise HTTPException(409, "payable Employee is not present in the approved Payroll run")
    tax = await session.scalar(select(PayrollTaxDeductionResultRecord).where(PayrollTaxDeductionResultRecord.company_id == context.company.id, PayrollTaxDeductionResultRecord.id == member.tax_result_id, PayrollTaxDeductionResultRecord.calculation_digest == member.tax_result_digest, PayrollTaxDeductionResultRecord.lifecycle == "approved"))
    if tax is None:
        raise HTTPException(409, "approved net-pay evidence is unavailable")
    digest = canonical_digest({"run_id": str(run_id), "employee_id": str(payload.employee_id), "check_number": payload.check_number, "issue_date": payload.issue_date.isoformat(), "amount": str(tax.net_pay_candidate)})
    existing = await session.scalar(select(PayrollPaperCheckEvidenceRecord).where(PayrollPaperCheckEvidenceRecord.company_id == context.company.id, PayrollPaperCheckEvidenceRecord.replay_identity == payload.idempotency_key))
    if existing is not None:
        if existing.evidence_digest != digest:
            raise HTTPException(409, "paper-check replay conflicts with the original evidence")
        return {"check_id": existing.id, "lifecycle": existing.lifecycle, "replayed": True, "amount": str(existing.amount), "execution": "not_performed"}
    value = PayrollPaperCheckEvidenceRecord(company_id=context.company.id, run_id=run_id, employee_id=payload.employee_id, amount=tax.net_pay_candidate, currency=tax.currency, check_number=payload.check_number, issue_date=payload.issue_date, lifecycle="issued", replay_identity=payload.idempotency_key, evidence_digest=digest, actor_user_id=context.user.id)
    session.add(value)
    AuditService.stage(session, AuditEntry(action="payroll.paper_check.issued", resource_type="payroll_paper_check", actor_user_id=context.user.id, company_id=context.company.id, resource_id=value.id, reason_code="paper_check_issued", details={"run_id": str(run_id), "employee_id": str(payload.employee_id), "amount": str(tax.net_pay_candidate)}))
    await session.commit()
    return {"check_id": value.id, "lifecycle": value.lifecycle, "replayed": False, "amount": str(value.amount), "execution": "not_performed"}


@router.post("/paper-checks/{check_id}/void")
async def void_paper_check(check_id: UUID, payload: PaperCheckVoidInput, context: PaymentManage, session: Session) -> dict[str, object]:
    value = await session.scalar(select(PayrollPaperCheckEvidenceRecord).where(PayrollPaperCheckEvidenceRecord.company_id == context.company.id, PayrollPaperCheckEvidenceRecord.id == check_id).with_for_update())
    if value is None:
        raise HTTPException(404, "paper-check evidence was not found")
    existing = await session.scalar(select(PayrollPaperCheckEvidenceRecord).where(PayrollPaperCheckEvidenceRecord.company_id == context.company.id, PayrollPaperCheckEvidenceRecord.replay_identity == payload.idempotency_key))
    if existing is not None:
        if existing.supersedes_id != value.id or existing.lifecycle != "voided":
            raise HTTPException(409, "paper-check void replay conflicts with the original evidence")
        return {"check_id": existing.id, "lifecycle": existing.lifecycle, "replayed": True}
    if value.lifecycle != "issued" and value.lifecycle != "reissued":
        raise HTTPException(409, "only issued paper-check evidence can be voided")
    value.lifecycle = "voided"
    replacement = PayrollPaperCheckEvidenceRecord(company_id=value.company_id, run_id=value.run_id, employee_id=value.employee_id, amount=value.amount, currency=value.currency, check_number=f"VOID-{value.check_number}-{str(value.id)[:8]}", issue_date=value.issue_date, lifecycle="voided", supersedes_id=value.id, replay_identity=payload.idempotency_key, evidence_digest=canonical_digest({"voids": str(value.id), "reason": payload.reason}), actor_user_id=context.user.id, void_reason=payload.reason)
    session.add(replacement)
    AuditService.stage(session, AuditEntry(action="payroll.paper_check.voided", resource_type="payroll_paper_check", actor_user_id=context.user.id, company_id=context.company.id, resource_id=value.id, reason_code="paper_check_voided", details={"replacement_id": str(replacement.id), "reason": payload.reason}))
    await session.commit()
    return {"check_id": replacement.id, "original_check_id": value.id, "lifecycle": replacement.lifecycle, "replayed": False}


@router.post("/runs/{run_id}/paper-checks/reissue")
async def reissue_paper_check(run_id: UUID, payload: PaperCheckReissueInput, context: PaymentManage, session: Session) -> dict[str, object]:
    original = await session.scalar(select(PayrollPaperCheckEvidenceRecord).where(PayrollPaperCheckEvidenceRecord.company_id == context.company.id, PayrollPaperCheckEvidenceRecord.id == payload.original_check_id, PayrollPaperCheckEvidenceRecord.run_id == run_id))
    if original is None or original.lifecycle != "voided":
        raise HTTPException(409, "voided original paper-check evidence is required")
    issue = PaperCheckIssueInput(employee_id=payload.employee_id, check_number=payload.check_number, issue_date=payload.issue_date, idempotency_key=payload.idempotency_key)
    result = await issue_paper_check(run_id, issue, context, session)
    return {**result, "reissued_from": original.id}


@router.get("/runs/{run_id}/payment-readiness")
async def payment_readiness(run_id: UUID, context: PaymentRead, session: Session) -> dict[str, object]:
    run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == run_id))
    if run is None:
        raise HTTPException(404, "Payroll run was not found")
    period = await session.scalar(select(PayPeriod).where(PayPeriod.company_id == context.company.id, PayPeriod.id == run.pay_period_id))
    if period is None:
        raise HTTPException(422, "Payroll pay period is unavailable")
    members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.company_id == context.company.id, PayrollRunMemberRecord.run_id == run.id, PayrollRunMemberRecord.disposition == "ready").order_by(PayrollRunMemberRecord.employee_id))).all())
    service = PayrollPaymentReleaseService()
    rows = []
    for member in members:
        resolution = await service.resolve_destination(session, company_id=context.company.id, employee_id=member.employee_id, as_of_date=period.payday)
        rows.append({"employee_id": member.employee_id, "state": resolution.state.value, "method": resolution.method.value if resolution.method else None, "masked": bool(resolution.protected_reference is not None)})
    return {"run_id": run.id, "run_lifecycle": run.lifecycle, "payday": period.payday, "payment_method": "paper_check", "instructions": rows, "execution": "not_performed"}


@router.post("/runs/{run_id}/paper-check-release/assemble")
async def assemble_paper_check_release(run_id: UUID, context: PaymentAssemble, session: Session) -> dict[str, object]:
    run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == run_id))
    if run is None:
        raise HTTPException(404, "Payroll run was not found")
    period = await session.scalar(select(PayPeriod).where(PayPeriod.company_id == context.company.id, PayPeriod.id == run.pay_period_id))
    if period is None:
        raise HTTPException(422, "Payroll pay period is unavailable")
    members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.company_id == context.company.id, PayrollRunMemberRecord.run_id == run.id, PayrollRunMemberRecord.disposition == "ready"))).all())
    service = PayrollPaymentReleaseService()
    destinations = {member.employee_id: await service.resolve_destination(session, company_id=context.company.id, employee_id=member.employee_id, as_of_date=period.payday) for member in members}
    try:
        candidate = await service.assemble_candidate(session, context=context, payroll_run_id=run.id, destinations=destinations, assembled_at=datetime.now(timezone.utc))
        value = await service.persist_candidate(session, context=context, candidate=candidate)
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"release_id": value.id, "lifecycle": value.lifecycle, "review_state": value.review_state, "aggregate_release_amount": str(value.aggregate_release_amount), "execution": "not_performed"}


@router.post("/paper-check-releases/{release_id}/review")
async def review_paper_check_release(release_id: UUID, payload: ReviewInput, context: PaymentReview, session: Session) -> dict[str, object]:
    try:
        value = await PayrollPaymentReleaseService().initiate_review(session, context=context, release_id=release_id, reason_code=payload.reason_code)
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"release_id": value.release_id, "decision": value.decision, "review_digest": value.review_digest}


@router.post("/paper-check-releases/{release_id}/review/decision")
async def decide_paper_check_review(release_id: UUID, payload: ReviewDecisionInput, context: PaymentReview, session: Session) -> dict[str, object]:
    try:
        value = await PayrollPaymentReleaseService().decide_review(session, context=context, release_id=release_id, decision=PaymentReleaseReviewDecision(payload.decision), reason_code=payload.reason_code)
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"release_id": value.release_id, "decision": value.decision, "review_digest": value.review_digest}


@router.post("/paper-check-releases/{release_id}/approve")
async def approve_paper_check_release(release_id: UUID, payload: ReviewInput, context: PaymentApprove, session: Session) -> dict[str, object]:
    try:
        value = await PayrollPaymentReleaseService().approve_release(session, context=context, release_id=release_id, reason_code=payload.reason_code)
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"release_id": value.release_id, "decision": value.decision, "review_digest": value.review_digest, "execution": "not_performed"}
