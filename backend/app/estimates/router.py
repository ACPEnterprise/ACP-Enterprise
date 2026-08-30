import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.estimates.artifact import render_estimate_artifact
from app.estimates.contracts import (
    CreateEstimateRevisionSpec,
    CreateEstimateSpec,
    EstimateDecisionSpec,
    EstimateLineSpec,
    EstimateRecord,
    EstimateTransitionSpec,
)
from app.estimates.errors import (
    EstimateConflictError,
    EstimateError,
    EstimateNotFoundError,
    EstimateValidationError,
)
from app.estimates.models import (
    CommercialPolicyVersion,
    Estimate,
    EstimateCustomerDecision,
    EstimateFollowUpEvidence,
    EstimateJobConversion,
    EstimateLifecycleHistory,
    EstimatePresentationAuthority,
    EstimateRevision,
)
from app.estimates.schemas import (
    CommercialHistoryItem,
    CommercialPolicyItem,
    CommercialPolicyWrite,
    CommercialReport,
    DecisionInput,
    EstimateArtifact,
    EstimateItem,
    EstimateList,
    FollowUpItem,
    FollowUpWrite,
    PresentationAuthorityItem,
    PresentationCredential,
    PresentationPrepareInput,
    ProposalInput,
    ProtectedEstimateDecision,
    ProtectedEstimateView,
    RevisionInput,
    TaxPolicyInput,
    TaxPolicyItem,
    TransitionInput,
)
from app.estimates.service import estimate_service
from app.events.models import BusinessEvent
from app.events.types import EventType
from app.platform.auth.tokens import SecurityTokenService
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


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def _scoped_estimate(
    session: AsyncSession, context: AuthorizationContext, estimate_id: UUID
) -> EstimateRecord:
    result = await estimate_service.repository.get(
        session, company_id=context.company.id, estimate_id=estimate_id
    )
    if result is None or result.branch_id not in {
        branch.id for branch in context.authorized_branches
    }:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate was not found.")
    return result


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


@router.get("/follow-ups", response_model=tuple[FollowUpItem, ...])
async def follow_up_queue(
    context: ReadContext,
    session: DatabaseSession,
    state_filter: str | None = Query(default=None, alias="state"),
) -> tuple[FollowUpItem, ...]:
    statement = select(EstimateFollowUpEvidence).where(
        EstimateFollowUpEvidence.company_id == context.company.id,
        EstimateFollowUpEvidence.branch_id.in_(
            tuple(branch.id for branch in context.authorized_branches)
        ),
    ).order_by(
        EstimateFollowUpEvidence.estimate_id,
        EstimateFollowUpEvidence.sequence.desc(),
    )
    rows = (await session.scalars(statement)).all()
    latest: dict[UUID, EstimateFollowUpEvidence] = {}
    for row in rows:
        latest.setdefault(row.estimate_id, row)
    values = tuple(
        FollowUpItem.model_validate(row)
        for row in latest.values()
        if state_filter is None or row.state == state_filter
    )
    return values


@router.get("/commercial-report", response_model=CommercialReport)
async def commercial_report(
    context: ReadContext, session: DatabaseSession
) -> CommercialReport:
    rows = (
        await session.execute(
            select(Estimate, EstimateRevision).join(
                EstimateRevision,
                (EstimateRevision.company_id == Estimate.company_id)
                & (EstimateRevision.id == Estimate.current_revision_id),
            ).where(
                Estimate.company_id == context.company.id,
                Estimate.branch_id.in_(
                    tuple(branch.id for branch in context.authorized_branches)
                ),
            )
        )
    ).all()
    converted_ids = set(
        (
            await session.scalars(
                select(EstimateJobConversion.estimate_id).where(
                    EstimateJobConversion.company_id == context.company.id
                )
            )
        ).all()
    )
    accepted: dict[str, Decimal] = {}
    outstanding: dict[str, Decimal] = {}
    for estimate, revision in rows:
        bucket = accepted if estimate.status == "approved" else outstanding
        if estimate.status in {"approved", "sent", "viewed"}:
            bucket[revision.currency] = bucket.get(revision.currency, Decimal(0)) + revision.total_amount
    return CommercialReport(
        created=len(rows),
        presented=sum(item.status in {"sent", "viewed", "approved", "rejected"} for item, _ in rows),
        viewed=sum(item.status == "viewed" for item, _ in rows),
        accepted=sum(item.status == "approved" for item, _ in rows),
        rejected=sum(item.status == "rejected" for item, _ in rows),
        expired=sum(item.status == "expired" for item, _ in rows),
        accepted_not_converted=sum(item.status == "approved" and item.id not in converted_ids for item, _ in rows),
        converted=len(converted_ids),
        accepted_value_by_currency=accepted,
        outstanding_value_by_currency=outstanding,
    )


@router.get("/protected-view", response_model=ProtectedEstimateView)
async def protected_estimate_view(
    session: DatabaseSession,
    x_estimate_access_token: Annotated[str, Header(min_length=32)],
) -> ProtectedEstimateView:
    token_digest = SecurityTokenService().hash_token(x_estimate_access_token)
    async with session.begin():
        authority = await session.scalar(
            select(EstimatePresentationAuthority)
            .where(EstimatePresentationAuthority.token_digest == token_digest)
            .with_for_update()
        )
        now = datetime.now(timezone.utc)
        if authority is None or authority.status in {"revoked", "superseded"} or (
            authority.expires_at is not None and authority.expires_at <= now
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate presentation is unavailable.")
        estimate = await estimate_service.repository.get(
            session, company_id=authority.company_id, estimate_id=authority.estimate_id
        )
        if estimate is None or estimate.current_revision.id != authority.revision_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Estimate presentation has been superseded.")
        if authority.status == "prepared":
            authority.status = "viewed"
            authority.viewed_at = now
            session.add(BusinessEvent(
                event_type=EventType.ESTIMATE_PRESENTATION_VIEWED.value,
                entity_type="estimate_presentation",
                entity_id=authority.id,
                company_id=authority.company_id,
                branch_id=authority.branch_id,
                user_id=authority.created_by_user_id,
                payload={"estimate_id": str(authority.estimate_id), "revision_id": str(authority.revision_id), "evidence_digest": authority.evidence_digest},
            ))
    item = EstimateItem.model_validate(estimate)
    return ProtectedEstimateView(
        presentation=PresentationAuthorityItem.model_validate(authority),
        artifact=render_estimate_artifact(item),
    )


@router.post("/protected-decision", response_model=EstimateItem)
async def protected_estimate_decision(
    payload: ProtectedEstimateDecision,
    session: DatabaseSession,
    x_estimate_access_token: Annotated[str, Header(min_length=32)],
) -> EstimateItem:
    token_digest = SecurityTokenService().hash_token(x_estimate_access_token)
    authority = await session.scalar(
        select(EstimatePresentationAuthority).where(
            EstimatePresentationAuthority.token_digest == token_digest
        )
    )
    now = datetime.now(timezone.utc)
    if authority is None or authority.status in {"revoked", "superseded"} or (
        authority.expires_at is not None and authority.expires_at <= now
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate presentation is unavailable.")
    if authority.revision_id != payload.revision_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Customer decision targets a stale Estimate revision.")
    if payload.decision == "reject" and not payload.rejection_reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Customer rejection requires a reason.")
    existing = await session.scalar(
        select(EstimateCustomerDecision).where(
            EstimateCustomerDecision.company_id == authority.company_id,
            EstimateCustomerDecision.revision_id == authority.revision_id,
        )
    )
    intended_decision = "approved" if payload.decision == "approve" else "rejected"
    evidence_reference = f"protected-presentation:{authority.id}"
    if existing is not None:
        equivalent = (
            existing.decision == intended_decision
            and existing.customer_name == payload.customer_name.strip()
            and existing.customer_email == payload.customer_email
            and existing.customer_comment == payload.customer_comment
            and existing.rejection_reason == payload.rejection_reason
            and existing.evidence_reference == evidence_reference
        )
        if not equivalent:
            raise HTTPException(status.HTTP_409_CONFLICT, "Customer decision conflicts with existing authority.")
        result = await estimate_service.repository.get(
            session,
            company_id=authority.company_id,
            estimate_id=authority.estimate_id,
        )
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate was not found.")
        return EstimateItem.model_validate(result)
    spec = EstimateDecisionSpec(
        company_id=authority.company_id,
        branch_id=authority.branch_id,
        estimate_id=authority.estimate_id,
        expected_version=authority.estimate_version,
        actor_user_id=authority.created_by_user_id,
        occurred_at=payload.occurred_at,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_comment=payload.customer_comment,
        rejection_reason=payload.rejection_reason,
        evidence_reference=evidence_reference,
    )
    await session.commit()
    try:
        result = await (
            estimate_service.approve(session, spec=spec)
            if payload.decision == "approve"
            else estimate_service.reject(session, spec=spec)
        )
    except EstimateError as error:
        raise _error(error) from error
    return EstimateItem.model_validate(result)


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


async def _enforce_discount_policy(
    session: AsyncSession,
    *,
    company_id: UUID,
    branch_id: UUID,
    discount_type: str | None,
    discount_value: Decimal | None,
) -> None:
    if discount_type is None or discount_value is None or discount_value == 0:
        return
    policy = await session.scalar(
        select(CommercialPolicyVersion)
        .where(
            CommercialPolicyVersion.company_id == company_id,
            CommercialPolicyVersion.branch_id == branch_id,
            CommercialPolicyVersion.policy_type == "discount",
        )
        .order_by(CommercialPolicyVersion.version.desc())
        .limit(1)
    )
    if policy is None or policy.status != "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Discount policy is unconfigured; Commercial override fails closed.",
        )
    mode = str(policy.configuration.get("mode", "prohibited"))
    if mode in {"prohibited", "no_override"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Commercial discount is prohibited by configured policy.")
    if mode == "approval_required":
        raise HTTPException(status.HTTP_409_CONFLICT, "Commercial discount requires separate approval evidence.")
    if mode != "permitted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Commercial discount policy mode is invalid.")
    maximum = policy.configuration.get(
        "maximum_percentage" if discount_type == "percentage" else "maximum_amount"
    )
    if maximum is None or discount_value > Decimal(str(maximum)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Commercial discount exceeds configured authority.")


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


@router.get(
    "/{estimate_id}/commercial-history",
    response_model=tuple[CommercialHistoryItem, ...],
)
async def estimate_commercial_history(
    estimate_id: UUID, context: ReadContext, session: DatabaseSession
) -> tuple[CommercialHistoryItem, ...]:
    await _scoped_estimate(session, context, estimate_id)
    lifecycle = (await session.scalars(select(EstimateLifecycleHistory).where(
        EstimateLifecycleHistory.company_id == context.company.id,
        EstimateLifecycleHistory.estimate_id == estimate_id,
    ))).all()
    followups = (await session.scalars(select(EstimateFollowUpEvidence).where(
        EstimateFollowUpEvidence.company_id == context.company.id,
        EstimateFollowUpEvidence.estimate_id == estimate_id,
    ))).all()
    presentations = (await session.scalars(select(EstimatePresentationAuthority).where(
        EstimatePresentationAuthority.company_id == context.company.id,
        EstimatePresentationAuthority.estimate_id == estimate_id,
    ))).all()
    decisions = (await session.scalars(select(EstimateCustomerDecision).where(
        EstimateCustomerDecision.company_id == context.company.id,
        EstimateCustomerDecision.estimate_id == estimate_id,
    ))).all()
    entries = [
        CommercialHistoryItem(evidence_type="lifecycle", state=row.to_status, occurred_at=row.occurred_at, actor_reference=row.actor_user_id, revision_id=None, evidence_digest=None, detail=row.reason)
        for row in lifecycle
    ] + [
        CommercialHistoryItem(evidence_type="follow_up", state=row.state, occurred_at=row.occurred_at, actor_reference=row.actor_user_id, revision_id=row.revision_id, evidence_digest=row.evidence_digest, detail=row.disposition)
        for row in followups
    ] + [
        CommercialHistoryItem(evidence_type="presentation", state=row.status, occurred_at=row.created_at, actor_reference=row.created_by_user_id, revision_id=row.revision_id, evidence_digest=row.evidence_digest, detail=row.channel)
        for row in presentations
    ] + [
        CommercialHistoryItem(evidence_type="customer_decision", state=row.decision, occurred_at=row.occurred_at, actor_reference=row.recorded_by_user_id, revision_id=row.revision_id, evidence_digest=None, detail=row.rejection_reason)
        for row in decisions
    ]
    return tuple(sorted(entries, key=lambda item: item.occurred_at))


@router.post(
    "/{estimate_id}/presentations",
    response_model=PresentationCredential,
    status_code=status.HTTP_201_CREATED,
)
async def prepare_estimate_presentation(
    estimate_id: UUID,
    payload: PresentationPrepareInput,
    context: ManageContext,
    session: DatabaseSession,
) -> PresentationCredential:
    _branch(context, payload.branch_id)
    estimate = await _scoped_estimate(session, context, estimate_id)
    if estimate.branch_id != payload.branch_id or estimate.status not in {"sent", "viewed"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only the current presented Estimate revision can receive protected access.",
        )
    artifact = render_estimate_artifact(EstimateItem.model_validate(estimate))
    estimate_pk = estimate.id
    revision_pk = estimate.current_revision.id
    revision_number = estimate.current_revision.revision_number
    requested = {
        "estimate_id": str(estimate_pk),
        "revision_id": str(revision_pk),
        "artifact_digest": artifact.artifact_digest,
        "recipient_reference": payload.recipient_reference,
        "channel": payload.channel,
        "expires_at": payload.expires_at,
    }
    evidence_digest = _digest(requested)
    token_service = SecurityTokenService()
    access_token = token_service.generate_token()
    async with session.begin_nested():
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"estimate-presentation:{context.company.id}:{payload.idempotency_key}"},
        )
        replay = await session.scalar(
            select(EstimatePresentationAuthority).where(
                EstimatePresentationAuthority.company_id == context.company.id,
                EstimatePresentationAuthority.idempotency_key == payload.idempotency_key,
            )
        )
        if replay is not None:
            if replay.evidence_digest != evidence_digest:
                raise HTTPException(status.HTTP_409_CONFLICT, "Presentation command identity was reused with contradictory evidence.")
            # Credentials are intentionally shown only once; replay cannot disclose them.
            raise HTTPException(status.HTTP_409_CONFLICT, "Presentation already exists; its access credential cannot be replayed.")
        authority = EstimatePresentationAuthority(
            company_id=context.company.id,
            branch_id=payload.branch_id,
            estimate_id=estimate_pk,
            revision_id=revision_pk,
            revision_number=revision_number,
            estimate_version=estimate.version,
            artifact_digest=artifact.artifact_digest,
            recipient_reference=payload.recipient_reference,
            channel=payload.channel,
            status="prepared",
            token_digest=token_service.hash_token(access_token),
            expires_at=payload.expires_at,
            evidence_digest=evidence_digest,
            idempotency_key=payload.idempotency_key,
            created_by_user_id=context.user.id,
        )
        session.add(authority)
        await session.flush()
        session.add(BusinessEvent(
            event_type=EventType.ESTIMATE_PRESENTATION_PREPARED.value,
            entity_type="estimate_presentation",
            entity_id=authority.id,
            company_id=context.company.id,
            branch_id=payload.branch_id,
            user_id=context.user.id,
            payload={"estimate_id": str(estimate_pk), "revision_id": str(revision_pk), "channel": payload.channel, "artifact_digest": artifact.artifact_digest, "evidence_digest": evidence_digest},
        ))
    await session.commit()
    return PresentationCredential(
        **PresentationAuthorityItem.model_validate(authority).model_dump(),
        access_token=access_token,
    )


@router.post("/{estimate_id}/follow-ups", response_model=FollowUpItem)
async def record_follow_up(
    estimate_id: UUID,
    payload: FollowUpWrite,
    context: ManageContext,
    session: DatabaseSession,
) -> FollowUpItem:
    _branch(context, payload.branch_id)
    estimate = await _scoped_estimate(session, context, estimate_id)
    if estimate.branch_id != payload.branch_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate was not found.")
    estimate_pk = estimate.id
    revision_pk = estimate.current_revision.id
    requested = {
        "estimate_id": str(estimate_pk),
        "revision_id": str(revision_pk),
        "assigned_user_id": str(payload.assigned_user_id),
        "state": payload.state,
        "due_at": payload.due_at,
        "disposition": payload.disposition,
        "occurred_at": payload.occurred_at,
    }
    evidence_digest = _digest(requested)
    async with session.begin_nested():
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"estimate-follow-up:{context.company.id}:{estimate_pk}"},
        )
        replay = await session.scalar(select(EstimateFollowUpEvidence).where(
            EstimateFollowUpEvidence.company_id == context.company.id,
            EstimateFollowUpEvidence.idempotency_key == payload.idempotency_key,
        ))
        if replay is not None:
            if replay.evidence_digest != evidence_digest:
                raise HTTPException(status.HTTP_409_CONFLICT, "Follow-up command identity was reused with contradictory evidence.")
            return FollowUpItem.model_validate(replay)
        latest = await session.scalar(select(EstimateFollowUpEvidence).where(
            EstimateFollowUpEvidence.company_id == context.company.id,
            EstimateFollowUpEvidence.estimate_id == estimate_pk,
        ).order_by(EstimateFollowUpEvidence.sequence.desc()).limit(1).with_for_update())
        if payload.state in {"completed", "canceled"} and not payload.disposition:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A completed or canceled follow-up requires a disposition.")
        record = EstimateFollowUpEvidence(
            company_id=context.company.id,
            branch_id=payload.branch_id,
            estimate_id=estimate_pk,
            revision_id=revision_pk,
            assigned_user_id=payload.assigned_user_id,
            state=payload.state,
            due_at=payload.due_at,
            disposition=payload.disposition,
            sequence=(latest.sequence if latest else 0) + 1,
            evidence_digest=evidence_digest,
            idempotency_key=payload.idempotency_key,
            actor_user_id=context.user.id,
            occurred_at=payload.occurred_at,
        )
        session.add(record)
        await session.flush()
        session.add(BusinessEvent(
            event_type=EventType.ESTIMATE_FOLLOW_UP_CHANGED.value,
            entity_type="estimate_follow_up",
            entity_id=record.id,
            company_id=context.company.id,
            branch_id=payload.branch_id,
            user_id=context.user.id,
            payload={"estimate_id": str(estimate_pk), "revision_id": str(revision_pk), "state": record.state, "sequence": record.sequence, "evidence_digest": evidence_digest},
        ))
    await session.commit()
    return FollowUpItem.model_validate(record)


@router.post("", response_model=EstimateItem, status_code=status.HTTP_201_CREATED)
async def create_estimate(
    payload: ProposalInput, context: ManageContext, session: DatabaseSession
) -> EstimateItem:
    _branch(context, payload.branch_id)
    await _enforce_discount_policy(
        session,
        company_id=context.company.id,
        branch_id=payload.branch_id,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
    )
    await session.commit()
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
    await _enforce_discount_policy(
        session,
        company_id=context.company.id,
        branch_id=payload.branch_id,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
    )
    await session.commit()
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
