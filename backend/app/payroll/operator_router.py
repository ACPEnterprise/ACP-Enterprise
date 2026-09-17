"""Authenticated operator composition over the existing Payroll authorities.

This router deliberately does not calculate, transmit, or post Payroll. It
exposes the governed run lifecycle only when prerequisite evidence exists.
"""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.payroll.contracts import PayrollConflictError, canonical_digest
from app.payroll.operations import PayrollOperationsService
from app.payroll.permissions import PayrollPermission
from app.payroll.run_finalization import (
    PayrollPopulationEvidence,
    PayrollRunDisposition,
    PayrollRunMemberInput,
    PayrollRunService,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/payroll/operator", tags=["Payroll Operator"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.REPORTING_READ))]
Assemble = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_ASSEMBLE))]
Review = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_REVIEW))]
Approve = Annotated[AuthorizationContext, Depends(require_permission(PayrollPermission.RUN_APPROVE))]


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


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: UUID, payload: ReviewInput, context: Approve, session: Session) -> dict[str, object]:
    value = await PayrollRunService().approve(session, context=context, run_id=run_id, reason_code=payload.reason_code, safe_note=payload.safe_note)
    return {"run_id": value.run_id, "decision": value.decision, "review_digest": value.review_digest}
