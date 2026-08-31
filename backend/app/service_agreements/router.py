from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import ServiceAgreementPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure
from app.service_agreements.schemas import (
    AgreementOut,
    BillingCreate,
    BillingOut,
    EnrollmentCreate,
    EntitlementMutation,
    EntitlementOut,
    PlanCreate,
    PlanOut,
    RenewalCreate,
    Transition,
    WorkspaceOut,
)
from app.service_agreements.service import (
    AgreementConflict,
    AgreementError,
    AgreementNotFound,
    agreement_service,
)

router = APIRouter(prefix="/api/v1/service-agreements", tags=["Service Agreements"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[
    AuthorizationContext, Depends(require_permission(ServiceAgreementPermission.READ))
]
Manage = Annotated[
    AuthorizationContext, Depends(require_permission(ServiceAgreementPermission.MANAGE))
]
Admin = Annotated[
    AuthorizationContext,
    Depends(require_permission(ServiceAgreementPermission.PLAN_MANAGE)),
]


def fail(error: AgreementError):
    if isinstance(error, AgreementNotFound):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Service Agreement resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        raise HTTPException(404, failure.detail())
    if isinstance(error, AgreementConflict):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Service Agreement operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        raise HTTPException(409, failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Service Agreement evidence is invalid or incomplete.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    raise HTTPException(422, failure.detail())


@router.get("/plans", response_model=list[PlanOut])
async def plans(c: Read, s: Session):
    return [
        PlanOut.model_validate(x)
        for x in await agreement_service.list_plans(
            s, c.company.id, c.authorized_branch_ids
        )
    ]


@router.post("/plans", response_model=PlanOut)
async def create_plan(p: PlanCreate, c: Admin, s: Session):
    if p.branch_id and not c.can_access_branch(p.branch_id):
        raise HTTPException(404, "Branch was not found.")
    return PlanOut.model_validate(
        await agreement_service.create_plan(s, c.company.id, c.user.id, p)
    )


@router.post("/plans/{plan_id}/activate", response_model=PlanOut)
async def activate_plan(plan_id: UUID, c: Admin, s: Session):
    try:
        return PlanOut.model_validate(
            await agreement_service.activate_plan(
                s, c.company.id, plan_id, c.authorized_branch_ids
            )
        )
    except AgreementError as e:
        fail(e)


@router.post("", response_model=AgreementOut)
async def enroll(p: EnrollmentCreate, c: Manage, s: Session):
    if not c.can_access_branch(p.branch_id):
        raise HTTPException(404, "Branch was not found.")
    try:
        return AgreementOut.model_validate(
            await agreement_service.enroll(s, c.company.id, c.user.id, p)
        )
    except AgreementError as e:
        fail(e)


@router.get("/workspace", response_model=WorkspaceOut)
async def workspace(c: Read, s: Session):
    agreements, entitlements = await agreement_service.workspace(
        s, c.company.id, c.authorized_branch_ids
    )
    return WorkspaceOut(
        agreements=agreements,
        entitlements=entitlements,
        active_count=sum(x.status == "active" for x in agreements),
        renewal_pending_count=sum(x.status == "renewal_pending" for x in agreements),
        service_due_count=sum(x.status == "due" for x in entitlements),
        billing_unconfigured_count=sum(
            x.plan_snapshot.get("billing_cadence") == "unconfigured" for x in agreements
        ),
    )


@router.post("/{agreement_id}/activate", response_model=AgreementOut)
async def activate(agreement_id: UUID, p: Transition, c: Manage, s: Session):
    try:
        return AgreementOut.model_validate(
            await agreement_service.transition(
                s,
                c.company.id,
                agreement_id,
                c.authorized_branch_ids,
                p.expected_version,
                "active",
                key=p.idempotency_key,
                actor=c.user.id,
            )
        )
    except AgreementError as e:
        fail(e)


@router.post("/{agreement_id}/cancel", response_model=AgreementOut)
async def cancel(agreement_id: UUID, p: Transition, c: Manage, s: Session):
    try:
        return AgreementOut.model_validate(
            await agreement_service.transition(
                s,
                c.company.id,
                agreement_id,
                c.authorized_branch_ids,
                p.expected_version,
                "cancelled",
                p.reason,
                p.idempotency_key,
                c.user.id,
            )
        )
    except AgreementError as e:
        fail(e)


@router.post("/{agreement_id}/renewal-review", response_model=AgreementOut)
async def renewal_review(agreement_id: UUID, p: Transition, c: Manage, s: Session):
    try:
        return AgreementOut.model_validate(
            await agreement_service.transition(
                s,
                c.company.id,
                agreement_id,
                c.authorized_branch_ids,
                p.expected_version,
                "renewal_pending",
                key=p.idempotency_key,
                actor=c.user.id,
            )
        )
    except AgreementError as e:
        fail(e)


@router.post("/{agreement_id}/entitlements", response_model=list[EntitlementOut])
async def generate(agreement_id: UUID, c: Manage, s: Session):
    try:
        return [
            EntitlementOut.model_validate(x)
            for x in await agreement_service.generate(
                s, c.company.id, agreement_id, c.authorized_branch_ids
            )
        ]
    except AgreementError as e:
        fail(e)


@router.post("/entitlements/{entitlement_id}/{action}", response_model=EntitlementOut)
async def mutate_entitlement(
    entitlement_id: UUID, action: str, p: EntitlementMutation, c: Manage, s: Session
):
    if action not in {"schedule_link", "job_link", "consume", "reverse_consumption"}:
        raise HTTPException(404, "Action was not found.")
    try:
        return EntitlementOut.model_validate(
            await agreement_service.mutate_entitlement(
                s,
                c.company.id,
                c.user.id,
                entitlement_id,
                c.authorized_branch_ids,
                action,
                p.idempotency_key,
                p.appointment_id,
                p.job_id,
                p.evidence_reference,
            )
        )
    except AgreementError as e:
        fail(e)


@router.post("/{agreement_id}/billing-occurrences", response_model=BillingOut)
async def billing(agreement_id: UUID, p: BillingCreate, c: Manage, s: Session):
    try:
        return BillingOut.model_validate(
            await agreement_service.billing_ready(
                s,
                c.company.id,
                c.user.id,
                agreement_id,
                c.authorized_branch_ids,
                p.period_start,
                p.period_end,
                p.idempotency_key,
            )
        )
    except AgreementError as e:
        fail(e)


@router.post("/{agreement_id}/renew", response_model=AgreementOut)
async def renew(agreement_id: UUID, p: RenewalCreate, c: Manage, s: Session):
    try:
        return AgreementOut.model_validate(
            await agreement_service.renew(
                s,
                c.company.id,
                c.user.id,
                agreement_id,
                c.authorized_branch_ids,
                p.successor_plan_id,
                p.start_date,
                p.end_date,
                p.expected_version,
                p.idempotency_key,
            )
        )
    except AgreementError as e:
        fail(e)
