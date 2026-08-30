from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.catalog import (
    NATIVE_FINANCIAL_SIGNAL_CATALOG,
    OPERATIONAL_SIGNAL_CATALOG,
)
from app.beacon.contracts import BeaconLifecycleAction, BeaconWorkflowAction
from app.beacon.errors import (
    BeaconSignalNotFoundError,
    BeaconSignalStaleError,
    BeaconSnoozeInvalidError,
    BeaconWorkflowConflictError,
    BeaconWorkflowOwnerInvalidError,
)
from app.beacon.escalation import ESCALATION_REGISTRY, escalation_service
from app.beacon.evidence_evaluation import EVIDENCE_EVALUATION_REGISTRY
from app.beacon.intelligence import build_intelligence_packet
from app.beacon.lifecycle import (
    RecordBeaconLifecycleAction,
    beacon_lifecycle_service,
)
from app.beacon.quality import EVIDENCE_QUALITY_SERVICE
from app.beacon.schemas import (
    BeaconIntelligencePacketResponse,
    BeaconLifecycleCommandRequest,
    BeaconLifecycleEventResponse,
    BeaconLifecycleHistoryResponse,
    BeaconSignalPage,
    BeaconSignalResponse,
    BeaconSnoozeCommandRequest,
    BeaconSystemReadinessResponse,
    BeaconWorkflowCommandRequest,
    BeaconWorkflowEventResponse,
    BeaconWorkflowHistoryResponse,
    BeaconWorkflowStateResponse,
    DefinitionQualityRegistryResponse,
    DefinitionQualitySemanticsResponse,
    EscalationProjectionResponse,
    EscalationRegistrationResponse,
    EscalationRegistryResponse,
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
from app.platform.permissions.dependencies import (
    require_any_permission,
    require_permission,
)
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

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
BeaconOwner = Annotated[
    AuthorizationContext,
    Depends(require_permission(BeaconPermission.OWN)),
]
BeaconAssigner = Annotated[
    AuthorizationContext,
    Depends(require_permission(BeaconPermission.ASSIGN)),
]
BeaconOwnerOrAssigner = Annotated[
    AuthorizationContext,
    Depends(require_any_permission(BeaconPermission.OWN, BeaconPermission.ASSIGN)),
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
    "/financial-control-catalog",
    response_model=OperationalSignalCatalogResponse,
    summary="List native financial workflow and Accounting control signals",
)
async def financial_control_signal_catalog(
    context: BeaconReader,
) -> OperationalSignalCatalogResponse:
    """Expose 007A definitions without mixing legacy financial-exposure ranking."""
    catalog = NATIVE_FINANCIAL_SIGNAL_CATALOG
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
    "/system-readiness",
    response_model=BeaconSystemReadinessResponse,
    summary="Read Beacon definition, source, and policy readiness",
)
async def beacon_system_readiness(
    context: BeaconReader,
) -> BeaconSystemReadinessResponse:
    evaluations = EVIDENCE_EVALUATION_REGISTRY.registrations
    escalations = ESCALATION_REGISTRY.registrations
    blockers = tuple(
        sorted(
            {
                *(item.blocker for item in evaluations if item.blocker),
                *(item.blocker for item in escalations if item.blocker),
            }
        )
    )
    return BeaconSystemReadinessResponse(
        catalog_id=OPERATIONAL_SIGNAL_CATALOG.catalog_id,
        catalog_digest=OPERATIONAL_SIGNAL_CATALOG.catalog_digest,
        company_id=context.company.id,
        active_branch_id=context.active_branch.id if context.active_branch else None,
        definitions_total=len(OPERATIONAL_SIGNAL_CATALOG.definitions),
        evaluable=sum(item.readiness.value == "evaluable" for item in evaluations),
        partially_evaluable=sum(
            item.readiness.value == "partially_evaluable" for item in evaluations
        ),
        not_evaluable=sum(
            item.readiness.value == "not_evaluable" for item in evaluations
        ),
        conflicting=sum(item.readiness.value == "conflicting" for item in evaluations),
        escalation_ready=sum(
            item.eligibility.value == "escalation_ready" for item in escalations
        ),
        escalation_policy_unconfigured=sum(
            item.eligibility.value == "policy_missing" for item in escalations
        ),
        source_blockers=blockers,
        production_policy_state="UNCONFIGURED",
        autonomous_action=False,
    )


@router.get(
    "/escalation-readiness",
    response_model=EscalationRegistryResponse,
    summary="List deterministic escalation eligibility",
)
async def escalation_readiness(context: BeaconReader) -> EscalationRegistryResponse:
    return EscalationRegistryResponse(
        catalog_id=OPERATIONAL_SIGNAL_CATALOG.catalog_id,
        catalog_digest=OPERATIONAL_SIGNAL_CATALOG.catalog_digest,
        company_id=context.company.id,
        active_branch_id=context.active_branch.id if context.active_branch else None,
        registrations=tuple(
            EscalationRegistrationResponse(
                definition_id=item.definition_id,
                definition_version=item.definition_version,
                family=item.family,
                evaluation_readiness=item.evaluation_readiness,
                eligibility=item.eligibility,
                rule_available=item.rule is not None,
                rule_id=item.rule.rule_id if item.rule else None,
                rule_version=item.rule.version if item.rule else None,
                rule_digest=item.rule.rule_digest if item.rule else None,
                blocker=item.blocker,
            )
            for item in ESCALATION_REGISTRY.registrations
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
    workflows = await beacon_workflow_service.current_for_conditions(
        session,
        context=context,
        condition_keys=tuple(
            item.condition_key for item in (*queue.active, *queue.snoozed)
        ),
    )

    async def response(item) -> BeaconSignalResponse:
        base = BeaconSignalResponse.model_validate(item)
        if item.evidence_quality is None:
            return base
        workflow = workflows.get(item.condition_key)
        escalation = escalation_service.project(
            item,
            company_id=context.company.id,
            branch_id=context.active_branch.id if context.active_branch else None,
            workflow=workflow,
        )
        return base.model_copy(
            update={
                "escalation": EscalationProjectionResponse.model_validate(escalation)
            }
        )

    return BeaconSignalPage(
        items=tuple([await response(item) for item in queue.active]),
        snoozed_items=tuple([await response(item) for item in queue.snoozed]),
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
    workflows = await beacon_workflow_service.current_for_conditions(
        session,
        context=context,
        condition_keys=tuple(item.signal.condition_key for item in queue.items),
    )
    items: list[OperationalWorkflowSignalResponse] = []
    for item in queue.items:
        workflow = workflows.get(item.signal.condition_key)
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
                escalation=EscalationProjectionResponse.model_validate(
                    escalation_service.project(
                        item.signal,
                        company_id=context.company.id,
                        branch_id=(
                            context.active_branch.id if context.active_branch else None
                        ),
                        workflow=workflow,
                    )
                ),
            )
        )
    return OperationalWorkflowQueueResponse(
        view=view,
        ranking_version=queue.ranking_version,
        ranking_digest=queue.ranking_digest,
        items=tuple(items),
    )


@router.get(
    "/signals/{signal_id}/intelligence-packet",
    response_model=BeaconIntelligencePacketResponse,
    summary="Read a permission-bounded deterministic signal evidence packet",
)
async def signal_intelligence_packet(
    signal_id: UUID,
    session: DatabaseSession,
    context: BeaconReader,
) -> BeaconIntelligencePacketResponse:
    queue = await beacon_query_service.get_operational_attention_queue(
        session, context=context
    )
    item = next(
        (candidate for candidate in queue.items if candidate.signal.id == signal_id),
        None,
    )
    if item is None:
        raise _lifecycle_http_error(
            BeaconSignalNotFoundError("The authorized signal was not found.")
        )
    workflow = await beacon_workflow_service.current(
        session, context=context, condition_key=item.signal.condition_key
    )
    escalation = escalation_service.project(
        item.signal,
        company_id=context.company.id,
        branch_id=context.active_branch.id if context.active_branch else None,
        workflow=workflow,
    )
    return BeaconIntelligencePacketResponse.model_validate(
        build_intelligence_packet(
            item,
            context=context,
            workflow=workflow,
            escalation=escalation,
        )
    )


def _lifecycle_http_error(error: Exception) -> HTTPException:
    if isinstance(error, BeaconSignalNotFoundError):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Beacon signal was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(error, (BeaconSignalStaleError, BeaconWorkflowConflictError)):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Beacon operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Beacon request requires correction.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail())


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
    except (BeaconWorkflowConflictError, BeaconWorkflowOwnerInvalidError) as error:
        raise _lifecycle_http_error(error) from error
    return BeaconWorkflowEventResponse.model_validate(event)


@router.post("/signals/{signal_id}/claim", response_model=BeaconWorkflowEventResponse)
async def claim_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconOwner,
    session: DatabaseSession,
):
    return await _workflow_mutation(
        signal_id, data, BeaconWorkflowAction.CLAIM, context, session
    )


@router.post("/signals/{signal_id}/assign", response_model=BeaconWorkflowEventResponse)
async def assign_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconAssigner,
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
    context: BeaconAssigner,
    session: DatabaseSession,
):
    return await _workflow_mutation(
        signal_id, data, BeaconWorkflowAction.TRANSFER, context, session
    )


@router.post("/signals/{signal_id}/release", response_model=BeaconWorkflowEventResponse)
async def release_signal(
    signal_id: UUID,
    data: BeaconWorkflowCommandRequest,
    context: BeaconOwnerOrAssigner,
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
