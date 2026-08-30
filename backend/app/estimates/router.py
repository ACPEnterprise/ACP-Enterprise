from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.estimates.contracts import (
    CreateEstimateRevisionSpec,
    CreateEstimateSpec,
    EstimateDecisionSpec,
    EstimateLineSpec,
    EstimateTransitionSpec,
)
from app.estimates.errors import (
    EstimateConflictError,
    EstimateError,
    EstimateNotFoundError,
    EstimateValidationError,
)
from app.estimates.schemas import (
    DecisionInput,
    EstimateItem,
    EstimateList,
    ProposalInput,
    RevisionInput,
    TaxPolicyInput,
    TaxPolicyItem,
    TransitionInput,
)
from app.estimates.service import estimate_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EstimatePermission
from app.platform.permissions.dependencies import require_permission
from app.tax_policy.models import OperationalTaxPolicy

router = APIRouter(prefix="/api/v1/estimates", tags=["Estimates"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(EstimatePermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(EstimatePermission.MANAGE))
]


def _error(error: EstimateError) -> HTTPException:
    if isinstance(error, EstimateNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, EstimateConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, EstimateValidationError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Estimate operation failed.")


def _branch(context: AuthorizationContext, branch_id: UUID) -> None:
    if branch_id not in {branch.id for branch in context.authorized_branches}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Branch access is denied.")


def _lines(payload: ProposalInput) -> tuple[EstimateLineSpec, ...]:
    return tuple(
        EstimateLineSpec(
            snapshot_id=line.snapshot_id,
            title=line.title,
            description=line.description,
        )
        for line in payload.lines
    )


@router.get("", response_model=EstimateList)
async def list_estimates(
    context: ReadContext,
    session: DatabaseSession,
    customer_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=250),
) -> EstimateList:
    items = await estimate_service.repository.list_summaries(
        session,
        company_id=context.company.id,
        branch_ids=frozenset(branch.id for branch in context.authorized_branches),
        customer_id=customer_id,
        status=status_filter,
        limit=limit,
    )
    return EstimateList(items=items, total=len(items))


@router.get("/{estimate_id}", response_model=EstimateItem)
async def get_estimate(
    estimate_id: UUID, context: ReadContext, session: DatabaseSession
) -> EstimateItem:
    result = await estimate_service.repository.get(
        session, company_id=context.company.id, estimate_id=estimate_id
    )
    if result is None or result.branch_id not in {
        branch.id for branch in context.authorized_branches
    }:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate was not found.")
    return EstimateItem.model_validate(result)


@router.post("", response_model=EstimateItem, status_code=status.HTTP_201_CREATED)
async def create_estimate(
    payload: ProposalInput, context: ManageContext, session: DatabaseSession
) -> EstimateItem:
    _branch(context, payload.branch_id)
    try:
        result = await estimate_service.create(
            session,
            spec=CreateEstimateSpec(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                customer_id=payload.customer_id,
                service_location_id=payload.service_location_id,
                actor_user_id=context.user.id,
                proposal_title=payload.proposal_title,
                customer_message=payload.customer_message,
                terms=payload.terms,
                expires_at=payload.expires_at,
                lines=_lines(payload),
                discount_type=payload.discount_type,
                discount_value=payload.discount_value,
            ),
        )
        return EstimateItem.model_validate(result)
    except EstimateError as error:
        raise _error(error) from error


@router.post("/{estimate_id}/revisions", response_model=EstimateItem)
async def revise_estimate(
    estimate_id: UUID,
    payload: RevisionInput,
    context: ManageContext,
    session: DatabaseSession,
) -> EstimateItem:
    _branch(context, payload.branch_id)
    try:
        result = await estimate_service.revise(
            session,
            spec=CreateEstimateRevisionSpec(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                estimate_id=estimate_id,
                expected_version=payload.expected_version,
                actor_user_id=context.user.id,
                proposal_title=payload.proposal_title,
                customer_message=payload.customer_message,
                terms=payload.terms,
                expires_at=payload.expires_at,
                lines=_lines(payload),
                discount_type=payload.discount_type,
                discount_value=payload.discount_value,
            ),
        )
        return EstimateItem.model_validate(result)
    except EstimateError as error:
        raise _error(error) from error


async def _transition(
    action: Callable[..., Awaitable[object]],
    estimate_id: UUID,
    payload: TransitionInput,
    context: AuthorizationContext,
    session: AsyncSession,
) -> EstimateItem:
    _branch(context, payload.branch_id)
    try:
        result = await action(
            session,
            spec=EstimateTransitionSpec(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                estimate_id=estimate_id,
                expected_version=payload.expected_version,
                actor_user_id=context.user.id,
                occurred_at=payload.occurred_at,
            ),
        )
        return EstimateItem.model_validate(result)
    except EstimateError as error:
        raise _error(error) from error


@router.post("/{estimate_id}/send", response_model=EstimateItem)
async def send_estimate(
    estimate_id: UUID,
    payload: TransitionInput,
    context: ManageContext,
    session: DatabaseSession,
) -> EstimateItem:
    return await _transition(
        estimate_service.send, estimate_id, payload, context, session
    )


@router.post("/{estimate_id}/view", response_model=EstimateItem)
async def view_estimate(
    estimate_id: UUID,
    payload: TransitionInput,
    context: ManageContext,
    session: DatabaseSession,
) -> EstimateItem:
    return await _transition(
        estimate_service.mark_viewed, estimate_id, payload, context, session
    )


@router.post("/{estimate_id}/expire", response_model=EstimateItem)
async def expire_estimate(
    estimate_id: UUID,
    payload: TransitionInput,
    context: ManageContext,
    session: DatabaseSession,
) -> EstimateItem:
    return await _transition(
        estimate_service.expire, estimate_id, payload, context, session
    )


@router.post("/{estimate_id}/approve", response_model=EstimateItem)
async def approve_estimate(
    estimate_id: UUID,
    payload: DecisionInput,
    context: ManageContext,
    session: DatabaseSession,
) -> EstimateItem:
    return await _decision(
        estimate_service.approve, estimate_id, payload, context, session
    )


@router.post("/{estimate_id}/reject", response_model=EstimateItem)
async def reject_estimate(
    estimate_id: UUID,
    payload: DecisionInput,
    context: ManageContext,
    session: DatabaseSession,
) -> EstimateItem:
    return await _decision(
        estimate_service.reject, estimate_id, payload, context, session
    )


async def _decision(
    action: Callable[..., Awaitable[object]],
    estimate_id: UUID,
    payload: DecisionInput,
    context: AuthorizationContext,
    session: AsyncSession,
) -> EstimateItem:
    _branch(context, payload.branch_id)
    try:
        result = await action(
            session,
            spec=EstimateDecisionSpec(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                estimate_id=estimate_id,
                expected_version=payload.expected_version,
                actor_user_id=context.user.id,
                occurred_at=payload.occurred_at,
                customer_name=payload.customer_name,
                customer_email=payload.customer_email,
                customer_comment=payload.customer_comment,
                rejection_reason=payload.rejection_reason,
                evidence_reference=payload.evidence_reference,
            ),
        )
        return EstimateItem.model_validate(result)
    except EstimateError as error:
        raise _error(error) from error


@router.post(
    "/tax-policies", response_model=TaxPolicyItem, status_code=status.HTTP_201_CREATED
)
async def create_tax_policy(
    payload: TaxPolicyInput, context: ManageContext, session: DatabaseSession
) -> TaxPolicyItem:
    if payload.branch_id is not None:
        _branch(context, payload.branch_id)
    if payload.expires_at is not None and payload.expires_at <= payload.effective_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Tax policy effective window is invalid.",
        )
    policy = OperationalTaxPolicy(
        id=uuid4(),
        company_id=context.company.id,
        branch_id=payload.branch_id,
        tax_classification_id=payload.tax_classification_id,
        currency=payload.currency,
        rate_basis_points=payload.rate_basis_points,
        version=payload.version,
        effective_at=payload.effective_at,
        expires_at=payload.expires_at,
        created_by_user_id=context.user.id,
    )
    async with session.begin():
        session.add(policy)
    return TaxPolicyItem.model_validate(policy)
