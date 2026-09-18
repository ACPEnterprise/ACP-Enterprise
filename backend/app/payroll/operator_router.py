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
from app.payroll.contracts import PayrollConflictError, canonical_digest
from app.payroll.models import (
    PayrollRunCloseRecord,
    PayrollRunMemberRecord,
    PayrollRunRecord,
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
from app.platform.audit.service import AuditEntry, AuditService
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


class PaperCheckDestinationInput(BaseModel):
    employee_id: UUID
    check_reference: str = Field(min_length=1, max_length=120)
    masked_display: str = Field(min_length=1, max_length=120)
    effective_start: date
    effective_end: date | None = None
    audit_reason: str = Field(min_length=1, max_length=500)


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
async def calculate_run(run_id: UUID, context: Calculate, session: Session) -> dict[str, object]:
    """Compose the existing calculation authorities for operator use.

    Calculation engines persist immutable gross/tax results before run assembly;
    this route never fabricates inputs or recalculates a closed run. It returns
    blocker evidence until those governed results exist, and otherwise exposes
    the exact result references bound to the run.
    """
    run = await session.scalar(select(PayrollRunRecord).where(PayrollRunRecord.company_id == context.company.id, PayrollRunRecord.id == run_id))
    if run is None:
        raise HTTPException(404, "Payroll run was not found")
    members = tuple((await session.scalars(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.company_id == context.company.id, PayrollRunMemberRecord.run_id == run.id))).all())
    blockers = _run_blockers(run, members)
    if blockers:
        raise HTTPException(409, {"code": "PAYROLL_CALCULATION_BLOCKED", "blockers": blockers})
    return {
        "run_id": run.id,
        "status": "calculated",
        "calculation": "existing_governed_results",
        "members": [{"employee_id": item.employee_id, "gross_result_id": item.gross_result_id, "tax_result_id": item.tax_result_id} for item in members],
        "run_digest": run.run_digest,
        "replay": "same immutable result references",
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
