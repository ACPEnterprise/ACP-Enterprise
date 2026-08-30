import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.estimates.artifact import render_estimate_artifact
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
from app.estimates.models import CommercialPolicyVersion
from app.estimates.schemas import (
    CommercialPolicyItem,
    CommercialPolicyWrite,
    DecisionInput,
    EstimateArtifact,
    EstimateItem,
    EstimateList,
    ProposalInput,
    RevisionInput,
    TaxPolicyInput,
    TaxPolicyItem,
    TransitionInput,
)
from app.estimates.service import estimate_service
from app.events.models import BusinessEvent
from app.events.types import EventType
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


@router.get("/commercial-policies", response_model=tuple[CommercialPolicyItem, ...])
async def commercial_policies(
    context: ReadContext, session: DatabaseSession
) -> tuple[CommercialPolicyItem, ...]:
    rows = (
        await session.scalars(
            select(CommercialPolicyVersion)
            .where(
                CommercialPolicyVersion.company_id == context.company.id,
                CommercialPolicyVersion.branch_id.in_(
                    tuple(branch.id for branch in context.authorized_branches)
                ),
            )
            .order_by(
                CommercialPolicyVersion.branch_id,
                CommercialPolicyVersion.policy_type,
                CommercialPolicyVersion.version.desc(),
            )
        )
    ).all()
    latest: dict[tuple[UUID, str], CommercialPolicyVersion] = {}
    for row in rows:
        latest.setdefault((row.branch_id, row.policy_type), row)
    return tuple(CommercialPolicyItem.model_validate(row) for row in latest.values())


@router.put("/commercial-policies", response_model=CommercialPolicyItem)
async def configure_commercial_policy(
    payload: CommercialPolicyWrite,
    context: ManageContext,
    session: DatabaseSession,
) -> CommercialPolicyItem:
    _branch(context, payload.branch_id)
    if payload.status == "unconfigured" and payload.configuration:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Unconfigured Commercial policy cannot contain assumed values.",
        )
    if payload.status == "active" and not payload.configuration:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Active Commercial policy requires explicit configuration.",
        )
    async with session.begin():
        replay = await session.scalar(
            select(CommercialPolicyVersion).where(
                CommercialPolicyVersion.company_id == context.company.id,
                CommercialPolicyVersion.idempotency_key == payload.idempotency_key,
            )
        )
        requested = payload.model_dump(
            mode="json", exclude={"idempotency_key", "expected_version"}
        )
        if replay is not None:
            existing = {
                "branch_id": str(replay.branch_id),
                "policy_type": replay.policy_type,
                "status": replay.status,
                "configuration": replay.configuration,
                "readiness_reason": replay.readiness_reason,
            }
            if existing != requested:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Commercial policy command identity was reused with contradictory evidence.",
                )
            return CommercialPolicyItem.model_validate(replay)
        current = await session.scalar(
            select(CommercialPolicyVersion)
            .where(
                CommercialPolicyVersion.company_id == context.company.id,
                CommercialPolicyVersion.branch_id == payload.branch_id,
                CommercialPolicyVersion.policy_type == payload.policy_type,
            )
            .order_by(CommercialPolicyVersion.version.desc())
            .limit(1)
            .with_for_update()
        )
        current_version = current.version if current else None
        if payload.expected_version != current_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Commercial policy changed; refresh authoritative readiness.",
            )
        version = (current_version or 0) + 1
        evidence = {
            "company_id": str(context.company.id),
            **requested,
            "version": version,
        }
        evidence_digest = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        record = CommercialPolicyVersion(
            company_id=context.company.id,
            branch_id=payload.branch_id,
            policy_type=payload.policy_type,
            status=payload.status,
            configuration=payload.configuration,
            readiness_reason=payload.readiness_reason,
            version=version,
            evidence_digest=evidence_digest,
            idempotency_key=payload.idempotency_key,
            created_by_user_id=context.user.id,
        )
        session.add(record)
        await session.flush()
        session.add(
            BusinessEvent(
                event_type=EventType.COMMERCIAL_POLICY_CONFIGURED.value,
                entity_type="commercial_policy",
                entity_id=record.id,
                company_id=context.company.id,
                branch_id=payload.branch_id,
                user_id=context.user.id,
                payload={
                    "policy_type": record.policy_type,
                    "status": record.status,
                    "version": record.version,
                    "evidence_digest": record.evidence_digest,
                },
            )
        )
    return CommercialPolicyItem.model_validate(record)


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


@router.get("/{estimate_id}/artifact", response_model=EstimateArtifact)
async def get_estimate_artifact(
    estimate_id: UUID, context: ReadContext, session: DatabaseSession
) -> EstimateArtifact:
    result = await estimate_service.repository.get(
        session, company_id=context.company.id, estimate_id=estimate_id
    )
    if result is None or result.branch_id not in {
        branch.id for branch in context.authorized_branches
    }:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate was not found.")
    return render_estimate_artifact(EstimateItem.model_validate(result))


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
