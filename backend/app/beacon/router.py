from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.catalog import OPERATIONAL_SIGNAL_CATALOG
from app.beacon.contracts import BeaconLifecycleAction, BeaconWorkflowAction
from app.beacon.errors import (
    BeaconSignalNotFoundError,
    BeaconSignalStaleError,
    BeaconSnoozeInvalidError,
    BeaconWorkflowConflictError,
    BeaconWorkflowOwnerInvalidError,
)
from app.beacon.evidence_evaluation import EVIDENCE_EVALUATION_REGISTRY
from app.beacon.lifecycle import (
    RecordBeaconLifecycleAction,
    beacon_lifecycle_service,
)
from app.beacon.quality import EVIDENCE_QUALITY_SERVICE
from app.beacon.schemas import (
    BeaconLifecycleCommandRequest,
    BeaconLifecycleEventResponse,
    BeaconLifecycleHistoryResponse,
    BeaconSignalPage,
    BeaconSignalResponse,
    BeaconSnoozeCommandRequest,
    BeaconWorkflowCommandRequest,
    BeaconWorkflowEventResponse,
    BeaconWorkflowHistoryResponse,
    BeaconWorkflowStateResponse,
    DefinitionQualityRegistryResponse,
    DefinitionQualitySemanticsResponse,
    EvidenceEvaluationRegistrationResponse,
    EvidenceEvaluationRegistryResponse,
    OperationalAttentionQueueResponse,
    OperationalRankingResponse,
    OperationalSignalCatalogResponse,
    OperationalSignalDefinitionResponse,
    OperationalWorkflowQueueResponse,
    OperationalWorkflowSignalResponse,
)
from app.beacon.service import SIGNAL_TTL, beacon_query_service
from app.beacon.workflow import BeaconWorkflowCommand, beacon_workflow_service
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AnalyticsPermission, BeaconPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/beacon", tags=["Beacon"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
BeaconReader = Annotated[
    AuthorizationContext,
    Depends(require_permission(AnalyticsPermission.READ)),
]
BeaconReviewer = Annotated[
    AuthorizationContext,
    Depends(require_permission(BeaconPermission.REVIEW)),
]


@router.get(
    "/operational-catalog",
    response_model=OperationalSignalCatalogResponse,
    summary="List the versioned operational exception catalog",
)
async def operational_signal_catalog(
    context: BeaconReader,
) -> OperationalSignalCatalogResponse:
    catalog = OPERATIONAL_SIGNAL_CATALOG
    return OperationalSignalCatalogResponse(
        catalog_id=catalog.catalog_id,
        version=catalog.version,
        catalog_digest=catalog.catalog_digest,
        company_id=context.company.id,
        active_branch_id=context.active_branch.id if context.active_branch else None,
        definitions=tuple(
            OperationalSignalDefinitionResponse.model_validate(
                {
                    **definition.payload(),
                    "definition_digest": definition.definition_digest,
                }
            )
            for definition in catalog.definitions
        ),
    )


@router.get(
    "/evaluation-readiness",
    response_model=EvidenceEvaluationRegistryResponse,
    summary="List evidence-bound evaluator readiness",
)
async def evidence_evaluation_readiness(
    context: BeaconReader,
) -> EvidenceEvaluationRegistryResponse:
    return EvidenceEvaluationRegistryResponse(
        catalog_id=OPERATIONAL_SIGNAL_CATALOG.catalog_id,
        catalog_digest=OPERATIONAL_SIGNAL_CATALOG.catalog_digest,
        company_id=context.company.id,
        active_branch_id=context.active_branch.id if context.active_branch else None,
        registrations=tuple(
            EvidenceEvaluationRegistrationResponse(
                definition_id=registration.definition_id,
                family=registration.family,
                readiness=registration.readiness,
                authoritative_source_contract=(
                    registration.authoritative_source_contract
                ),
                required_fact_contract=registration.required_fact_contract,
                evaluator_implemented=registration.evaluator_implemented,
                blocker=registration.blocker,
                limitations=registration.limitations,
            )
            for registration in EVIDENCE_EVALUATION_REGISTRY.registrations
        ),
    )


@router.get(
    "/quality-semantics",
    response_model=DefinitionQualityRegistryResponse,
    summary="List deterministic confidence and freshness semantics",
)
async def signal_quality_semantics(
    context: BeaconReader,
) -> DefinitionQualityRegistryResponse:
    return DefinitionQualityRegistryResponse(
        catalog_id=OPERATIONAL_SIGNAL_CATALOG.catalog_id,
        catalog_digest=OPERATIONAL_SIGNAL_CATALOG.catalog_digest,
        company_id=context.company.id,
        active_branch_id=context.active_branch.id if context.active_branch else None,
        definitions=tuple(
            DefinitionQualitySemanticsResponse.model_validate(
                semantics, from_attributes=True
            )
            for semantics in EVIDENCE_QUALITY_SERVICE.semantics()
        ),
    )


@router.get(
    "/signals",
    response_model=BeaconSignalPage,
    summary="List deterministic operational signals",
)
async def list_beacon_signals(
    session: DatabaseSession,
    context: BeaconReader,
) -> BeaconSignalPage:
    evaluated_at = datetime.now(timezone.utc)
    queue = await beacon_query_service.get_attention_queue(
        session,
        context=context,
        now=evaluated_at,
    )
    return BeaconSignalPage(
        items=tuple(BeaconSignalResponse.model_validate(item) for item in queue.active),
        snoozed_items=tuple(
            BeaconSignalResponse.model_validate(item) for item in queue.snoozed
        ),
        evaluated_at=evaluated_at,
        expires_at=evaluated_at + SIGNAL_TTL,
        lifecycle_commands_available=context.has_permission(BeaconPermission.REVIEW),
    )


@router.get(
    "/operational-signals",
    response_model=OperationalAttentionQueueResponse,
    summary="List deterministically prioritized admitted operational signals",
)
async def list_prioritized_operational_signals(
    session: DatabaseSession,
    context: BeaconReader,
) -> OperationalAttentionQueueResponse:
    queue = await beacon_query_service.get_operational_attention_queue(
        session, context=context
    )
    return OperationalAttentionQueueResponse.model_validate(queue, from_attributes=True)


@router.get(
    "/operational-signals/workflow",
    response_model=OperationalWorkflowQueueResponse,
    summary="List operational attention with explicit workflow filters",
)
async def list_operational_workflow_signals(
    session: DatabaseSession,
    context: BeaconReader,
    view: Literal["all", "unowned", "mine", "acknowledged"] = "all",
) -> OperationalWorkflowQueueResponse:
    queue = await beacon_query_service.get_operational_attention_queue(
        session, context=context
    )
    items: list[OperationalWorkflowSignalResponse] = []
    for item in queue.items:
        workflow = await beacon_workflow_service.current(
            session, context=context, condition_key=item.signal.condition_key
        )
        if view == "unowned" and workflow and workflow.owner_user_id is not None:
            continue
        if view == "mine" and (
            workflow is None or workflow.owner_user_id != context.user.id
        ):
            continue
        if view == "acknowledged" and (workflow is None or not workflow.acknowledged):
            continue
        items.append(
            OperationalWorkflowSignalResponse(
                signal=BeaconSignalResponse.model_validate(item.signal),
                ranking=OperationalRankingResponse.model_validate(item.ranking),
                workflow=(
                    BeaconWorkflowStateResponse.model_validate(workflow)
                    if workflow
                    else None
                ),
            )
        )
    return OperationalWorkflowQueueResponse(
        view=view,
        ranking_version=queue.ranking_version,
        ranking_digest=queue.ranking_digest,
        items=tuple(items),
    )


def _lifecycle_http_error(error: Exception) -> HTTPException:
    if isinstance(error, BeaconSignalNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, BeaconSignalStaleError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error))


async def _record_action(
    *,
    signal_id,
    evidence_digest: str,
    action: BeaconLifecycleAction,
    context: AuthorizationContext,
    session: AsyncSession,
    snooze_until: datetime | None = None,
) -> BeaconLifecycleEventResponse:
    try:
        event = await beacon_lifecycle_service.record(
            session,
            context=context,
            command=RecordBeaconLifecycleAction(
                signal_id=signal_id,
                evidence_digest=evidence_digest,
                action=action,
                snooze_until=snooze_until,
            ),
        )
    except (
        BeaconSignalNotFoundError,
        BeaconSignalStaleError,
        BeaconSnoozeInvalidError,
    ) as error:
        raise _lifecycle_http_error(error) from error
    return BeaconLifecycleEventResponse.model_validate(event)


@router.post(
    "/signals/{signal_id}/acknowledge",
    response_model=BeaconWorkflowEventResponse,
)
async def acknowledge_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconReviewer,
    session: DatabaseSession,
) -> BeaconWorkflowEventResponse:
    try:
        event = await beacon_workflow_service.mutate(
            session,
            context=context,
            command=BeaconWorkflowCommand(
                signal_id=signal_id,
                evidence_digest=data.evidence_digest,
                request_id=data.request_id,
                action=BeaconWorkflowAction.ACKNOWLEDGE,
            ),
        )
    except (BeaconSignalNotFoundError, BeaconSignalStaleError) as error:
        raise _lifecycle_http_error(error) from error
    return BeaconWorkflowEventResponse.model_validate(event)


async def _workflow_mutation(signal_id, data, action, context, session):
    try:
        event = await beacon_workflow_service.mutate(
            session,
            context=context,
            command=BeaconWorkflowCommand(
                signal_id=signal_id,
                evidence_digest=data.evidence_digest,
                request_id=data.request_id,
                action=action,
                expected_version=data.expected_version,
                owner_user_id=data.owner_user_id,
            ),
        )
    except (BeaconSignalNotFoundError, BeaconSignalStaleError) as error:
        raise _lifecycle_http_error(error) from error
    except BeaconWorkflowConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except BeaconWorkflowOwnerInvalidError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return BeaconWorkflowEventResponse.model_validate(event)


@router.post("/signals/{signal_id}/claim", response_model=BeaconWorkflowEventResponse)
async def claim_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconReader,
    session: DatabaseSession,
):
    return await _workflow_mutation(
        signal_id, data, BeaconWorkflowAction.CLAIM, context, session
    )


@router.post("/signals/{signal_id}/assign", response_model=BeaconWorkflowEventResponse)
async def assign_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconReader,
    session: DatabaseSession,
):
    return await _workflow_mutation(
        signal_id, data, BeaconWorkflowAction.ASSIGN, context, session
    )


@router.post(
    "/signals/{signal_id}/transfer", response_model=BeaconWorkflowEventResponse
)
async def transfer_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconReader,
    session: DatabaseSession,
):
    return await _workflow_mutation(
        signal_id, data, BeaconWorkflowAction.TRANSFER, context, session
    )


@router.post("/signals/{signal_id}/release", response_model=BeaconWorkflowEventResponse)
async def release_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconReader,
    session: DatabaseSession,
):
    return await _workflow_mutation(
        signal_id, data, BeaconWorkflowAction.RELEASE, context, session
    )


@router.get("/workflow", response_model=BeaconWorkflowStateResponse | None)
async def current_workflow(
    condition_key: UUID, context: BeaconReader, session: DatabaseSession
):
    state = await beacon_workflow_service.current(
        session, context=context, condition_key=condition_key
    )
    return BeaconWorkflowStateResponse.model_validate(state) if state else None


@router.get("/workflow-history", response_model=BeaconWorkflowHistoryResponse)
async def workflow_history(
    condition_key: UUID,
    context: BeaconReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    events = await beacon_workflow_service.history(
        session, context=context, condition_key=condition_key, limit=limit
    )
    return BeaconWorkflowHistoryResponse(
        items=tuple(BeaconWorkflowEventResponse.model_validate(item) for item in events)
    )


@router.post(
    "/signals/{signal_id}/review",
    response_model=BeaconLifecycleEventResponse,
)
async def review_signal(
    signal_id: UUID,
    data: BeaconLifecycleCommandRequest,
    context: BeaconReviewer,
    session: DatabaseSession,
) -> BeaconLifecycleEventResponse:
    return await _record_action(
        signal_id=signal_id,
        evidence_digest=data.evidence_digest,
        action=BeaconLifecycleAction.REVIEW,
        context=context,
        session=session,
    )


@router.post(
    "/signals/{signal_id}/snooze",
    response_model=BeaconLifecycleEventResponse,
)
async def snooze_signal(
    signal_id: UUID,
    data: BeaconSnoozeCommandRequest,
    context: BeaconReviewer,
    session: DatabaseSession,
) -> BeaconLifecycleEventResponse:
    return await _record_action(
        signal_id=signal_id,
        evidence_digest=data.evidence_digest,
        action=BeaconLifecycleAction.SNOOZE,
        snooze_until=data.snooze_until,
        context=context,
        session=session,
    )


@router.get(
    "/lifecycle-events",
    response_model=BeaconLifecycleHistoryResponse,
)
async def lifecycle_history(
    condition_key: UUID,
    context: BeaconReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BeaconLifecycleHistoryResponse:
    events = await beacon_lifecycle_service.history(
        session,
        context=context,
        condition_key=condition_key,
        limit=limit,
    )
    return BeaconLifecycleHistoryResponse(
        items=tuple(
            BeaconLifecycleEventResponse.model_validate(item) for item in events
        )
    )
