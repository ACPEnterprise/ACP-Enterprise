"""Authenticated operator composition over the existing Payroll authorities.

This router deliberately does not calculate, transmit, or post Payroll. It
exposes the governed run lifecycle only when prerequisite evidence exists.
"""
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.payroll.contracts import PayrollConflictError, canonical_digest
from app.payroll.models import PayrollRunMemberRecord, PayrollRunRecord
from app.payroll.operations import PayrollOperationsService
from app.payroll.payment_release import (
    DraftPaymentDestination,
    PaymentMethod,
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
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission
from app.timekeeping.models import PayPeriod

router = APIRouter(prefix="/api/v1/payroll/operator", tags=["Payroll Operator"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.REPORTING_READ))]
Assemble = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_ASSEMBLE))]
Review = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_REVIEW))]
Approve = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_APPROVE))]
PaymentRead = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.PAYMENT_RELEASE_READ))]
PaymentManage = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.PAYMENT_INSTRUCTION_MANAGE))]


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


class PaperCheckDestinationInput(BaseModel):
    employee_id: UUID
    check_reference: str = Field(min_length=1, max_length=120)
    masked_display: str = Field(min_length=1, max_length=120)
    effective_start: date
    effective_end: date | None = None
    audit_reason: str = Field(min_length=1, max_length=500)


class ReviewDecisionInput(ReviewInput):
    decision: str = Field(pattern="^(accepted|rejected)$")


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


@router.post("/paper-check-destinations")
async def create_paper_check_destination(payload: PaperCheckDestinationInput, context: PaymentManage, session: Session) -> dict[str, object]:
    employee = await session.scalar(
        select(Employee).where(Employee.company_id == context.company.id, Employee.id == payload.employee_id, Employee.status == "active")
    )
    if employee is None:
        raise HTTPException(404, "active Employee was not found in this Company")
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
    return {"destination_id": value.id, "employee_id": value.employee_id, "method": value.method_type, "lifecycle": value.lifecycle, "masked_display": value.masked_display}


@router.post("/paper-check-destinations/{destination_id}/approve")
async def approve_paper_check_destination(destination_id: UUID, context: PaymentManage, session: Session) -> dict[str, object]:
    try:
        value = await PayrollPaymentReleaseService().approve_destination(session, context=context, destination_id=destination_id)
    except (PayrollConflictError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"destination_id": value.id, "employee_id": value.employee_id, "method": value.method_type, "lifecycle": value.lifecycle, "masked_display": value.masked_display}


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
