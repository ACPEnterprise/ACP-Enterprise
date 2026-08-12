import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.engineering_capacity.service import engineering_capacity_service
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CancelEngineeringCommand,
)
from app.engineering_control.errors import EngineeringControlError
from app.engineering_control.http_errors import engineering_http_error
from app.engineering_control.scheduler.reconciliation import (
    scheduler_reconciliation_service,
)
from app.engineering_control.scheduler.schemas import SchedulerReconciliationReport
from app.engineering_control.workstream_runtime import EngineeringWorkstreamRuntime
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import require_permission

from .external_adoption import (
    ExternalAdoptionError,
    ExternalMilestoneAdoption,
    external_adoption_service,
)
from .notifications import mission_notification_service
from .realtime import InvalidResumeToken, event_stream, validate_resume_token
from .roadmaps import roadmap_service
from .schemas import (
    ExternalAdoptionCreate,
    ExternalAdoptionItem,
    ExternalEvidenceCreate,
    MilestoneActionRequest,
    MilestoneItem,
    MissionNotificationAcknowledgement,
    MissionNotificationItem,
    MissionNotificationPage,
    MissionNotificationTransition,
    MobileApprovalRequest,
    MobileCancellationRequest,
    MobileCommandDetail,
    MobileCommandPage,
    MobileOwnerReviewPage,
    MobileWorkstreamActionRequest,
    MobileWorkstreamActionResult,
    MobileWorkstreamDetail,
    MobileWorkstreamPage,
    RoadmapCreate,
    RoadmapItem,
    RoadmapPage,
)
from .service import mobile_engineering_control_service

router = APIRouter(
    prefix="/api/v1/engineering/mobile", tags=["Mobile Engineering Control"]
)
logger = logging.getLogger(__name__)
ProjectionItem = TypeVar("ProjectionItem", bound=BaseModel)


def _bounded_projection(
    records: tuple[object, ...], schema: type[ProjectionItem], resource: str
) -> tuple[tuple[ProjectionItem, ...], tuple[str, ...]]:
    items: list[ProjectionItem] = []
    warnings: list[str] = []
    for record in records:
        try:
            items.append(schema.model_validate(record))
        except ValidationError:
            record_id = getattr(record, "id", "unknown")
            logger.exception(
                "Mission Control omitted invalid %s projection id=%s",
                resource,
                record_id,
            )
            warnings.append(
                f"One {resource} record is unavailable because its stored definition is invalid."
            )
    return tuple(items), tuple(warnings)


DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.READ)),
]
ManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.MANAGE)),
]
ApproveContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.APPROVE)),
]


@router.get(
    "/scheduler/reconciliation/dry-run",
    response_model=SchedulerReconciliationReport,
    summary="Build a zero-write MMQ scheduler reconciliation plan",
)
async def scheduler_reconciliation_dry_run(
    context: ApproveContext,
    session: DatabaseSession,
) -> SchedulerReconciliationReport:
    report = await scheduler_reconciliation_service.dry_run(
        session, company_id=context.company.id
    )
    await session.rollback()
    return report


def _attention(
    item: MilestoneItem,
    adoption: ExternalAdoptionItem | None,
    runtime: EngineeringWorkstreamRuntime | None,
    capacity_state: str | None = None,
    capacity_reason: str | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    if capacity_state == "reconciliation":
        return (
            "owner_action_required",
            capacity_reason
            or "Execution outcome requires authoritative reconciliation.",
            ("request_revision", "cancel"),
        )
    if item.reconciliation_state != "current":
        return (
            "waiting_on_dependency",
            f"Scheduler reconciliation required: {item.reconciliation_state}.",
            (),
        )
    if adoption is not None:
        if adoption.status == "waiting_review":
            return (
                "owner_action_required",
                "External completion is ready for your review.",
                ("approve", "request_revision", "reject"),
            )
        if adoption.status not in {"completed", "cancelled", "archived"}:
            reason = (
                "Waiting for authenticated external evidence."
                if adoption.status == "pending_start"
                else "External work is progressing outside Mission Control."
            )
            return "waiting_on_external", reason, ()
    if (
        runtime is not None
        and runtime.runtime_state == "recovering"
        and runtime.reason_code
        in {
            "reconciliation_required",
            "ambiguous_interrupted_execution",
        }
    ):
        return (
            "owner_action_required",
            "A manual recovery decision is required.",
            ("request_revision", "cancel"),
        )
    if item.status == "ready" and item.readiness_state == "ready":
        return (
            "owner_action_required",
            "This milestone is ready to start.",
            ("start", "skip"),
        )
    if item.status == "waiting_review":
        return (
            "owner_action_required",
            "Completed work is ready for your review.",
            ("approve", "request_revision", "reject"),
        )
    if item.status == "waiting_approval":
        return (
            "owner_action_required",
            "An approval decision is required.",
            ("approve", "reject", "skip"),
        )
    if item.status == "running":
        if capacity_state == "available" and (
            runtime is None or runtime.runtime_state in {"queued", "acknowledged"}
        ):
            return (
                "running",
                "Authorized — awaiting automatic worker dispatch.",
                (),
            )
        if capacity_state in {"waiting", "reserved"}:
            return (
                "waiting_on_capacity",
                (
                    "Authenticated capacity is reserved and awaiting allocation."
                    if capacity_state == "reserved"
                    else capacity_reason
                    or "Execution is queued for authenticated worker capacity."
                ),
                (),
            )
        if capacity_state == "allocated":
            return "running", "Execution is in progress with tracked capacity.", ()
        if runtime is None or runtime.runtime_state in {"queued", "recovering"}:
            return (
                "waiting_on_capacity",
                "Execution is queued for authenticated worker capacity.",
                (),
            )
        if runtime.runtime_state in {"running", "validating", "deploying_preview"}:
            return (
                "running",
                "Running outside capacity tracking; no allocation is claimed.",
                (),
            )
        if runtime.runtime_state == "acknowledged":
            return (
                "running",
                "Authorized — awaiting automatic worker dispatch.",
                (),
            )
        return "running", "Execution is in progress.", ()
    if item.status in {"externally_running"}:
        return "waiting_on_external", "External work is in progress.", ()
    if item.status in {"draft", "planned", "blocked"}:
        dependency = (
            item.dependencies[-1] if item.dependencies else "an approved prerequisite"
        )
        return "waiting_on_dependency", f"Waiting for {dependency}.", ()
    return "informational", "No owner action is required.", ()


@router.post(
    "/roadmaps",
    response_model=RoadmapItem,
    summary="Create a versioned Engineering roadmap",
)
async def create_roadmap(
    request: RoadmapCreate, context: ManageContext, session: DatabaseSession
) -> RoadmapItem:
    return RoadmapItem.model_validate(
        await roadmap_service.create(session, context=context, payload=request)
    )


@router.get(
    "/roadmaps",
    response_model=RoadmapPage,
    summary="List roadmap and exact actionable dispatch truth",
)
async def list_roadmaps(context: ReadContext, session: DatabaseSession) -> RoadmapPage:
    roadmaps = await roadmap_service.list(session, context=context)
    milestones = await roadmap_service.milestones(session, context=context)
    adoptions = {
        item.milestone_id: item
        for item in await external_adoption_service.list(
            session, company_id=context.company.id
        )
    }
    adoption_items: dict[UUID, ExternalAdoptionItem] = {}
    for milestone_id, adoption in adoptions.items():
        latest = await external_adoption_service.latest_evidence(
            session,
            company_id=context.company.id,
            adoption_id=adoption.id,
        )
        stale = (
            adoption.last_evidence_at is not None
            and adoption.last_evidence_at
            <= datetime.now(timezone.utc) - timedelta(hours=24)
        )
        next_action = {
            "pending_start": "await_authenticated_start_evidence",
            "externally_running": "monitor_external_progress",
            "externally_validating": "monitor_external_validation",
            "externally_blocked": "resolve_external_blocker",
            "waiting_review": "review_external_completion",
            "revision_requested": "await_external_revision",
            "completed": "none",
            "cancelled": "none",
            "archived": "none",
        }[adoption.status]
        adoption_items[milestone_id] = ExternalAdoptionItem.model_validate(
            adoption
        ).model_copy(
            update={
                "validation_summary": tuple(latest.validation_results)
                if latest
                else (),
                "blockers": tuple(latest.blockers) if latest else (),
                "evidence_stale": stale,
                "next_owner_action": next_action,
            }
        )
    roadmap_items, roadmap_warnings = _bounded_projection(
        roadmaps, RoadmapItem, "roadmap"
    )
    milestone_items, milestone_warnings = _bounded_projection(
        milestones, MilestoneItem, "milestone"
    )
    command_ids = tuple(item.command_id for item in milestone_items if item.command_id)
    runtimes = {
        item.command_id: item
        for item in (
            (
                await session.scalars(
                    select(EngineeringWorkstreamRuntime).where(
                        EngineeringWorkstreamRuntime.company_id == context.company.id,
                        EngineeringWorkstreamRuntime.command_id.in_(command_ids),
                    )
                )
            ).all()
            if command_ids
            else ()
        )
    }
    capacity = await engineering_capacity_service.summary(session, context=context)
    capacity_states = {
        item.command_id: (
            "reconciliation"
            if item.decision == "reconciliation_required"
            else "available"
            if item.decision == "capacity_available"
            else "waiting"
        )
        for item in capacity.waiting_workstreams
    }
    capacity_reasons = {
        item.command_id: item.reason for item in capacity.waiting_workstreams
    }
    capacity_states.update(
        {item.command_id: "reserved" for item in capacity.active_reservations}
    )
    capacity_states.update(
        {item.command_id: "allocated" for item in capacity.active_allocations}
    )
    milestone_items = tuple(
        item.model_copy(
            update={
                "external_adoption": adoption_items.get(item.id),
                "attention_class": attention[0],
                "attention_reason": attention[1],
                "available_owner_actions": attention[2],
            }
        )
        for item in milestone_items
        for attention in (
            _attention(
                item,
                adoption_items.get(item.id),
                runtimes.get(item.command_id) if item.command_id else None,
                capacity_states.get(item.command_id) if item.command_id else None,
                capacity_reasons.get(item.command_id) if item.command_id else None,
            ),
        )
    )
    capacity_summary = (
        f"{capacity.available_capacity} available · "
        f"{capacity.allocated_capacity} allocated · "
        f"{capacity.reserved_capacity} reserved"
    )
    capacity_ids = [
        item.id
        for item in milestone_items
        if item.attention_class == "waiting_on_capacity"
    ]
    milestone_items = tuple(
        item.model_copy(
            update={
                "worker_capacity_summary": capacity_summary,
                "queue_position": capacity_ids.index(item.id) + 1,
            }
        )
        if item.id in capacity_ids
        else item
        for item in milestone_items
    )
    valid_milestone_ids = {item.id for item in milestone_items}
    milestones = tuple(item for item in milestones if item.id in valid_milestone_ids)
    item_by_id = {item.id: item for item in milestone_items}
    actionable = tuple(
        item
        for item in milestone_items
        if item.attention_class == "owner_action_required"
    )
    current = tuple(
        item
        for item in milestones
        if item.status
        in {"ready", "running", "externally_running", "paused", "waiting_review"}
    )
    next_ids: set[UUID] = set()
    for roadmap in roadmaps:
        candidate = next(
            (
                item
                for item in sorted(milestones, key=lambda value: value.position)
                if item.roadmap_id == roadmap.id
                and item.status == "planned"
                and item.definition_approved
            ),
            None,
        )
        if candidate is not None:
            next_ids.add(candidate.id)
    next_approved = tuple(item for item in milestones if item.id in next_ids)
    future = tuple(
        item
        for item in milestones
        if item.status in {"planned", "draft"} and item.id not in next_ids
    )
    completed = tuple(item for item in milestones if item.status == "completed")
    blocked = tuple(item for item in milestones if item.status == "blocked")
    running_items = tuple(
        item for item in milestone_items if item.attention_class == "running"
    )
    dependency_items = tuple(
        item
        for item in milestone_items
        if item.attention_class == "waiting_on_dependency"
    )
    capacity_items = tuple(
        item
        for item in milestone_items
        if item.attention_class == "waiting_on_capacity"
    )
    external_items = tuple(
        item
        for item in milestone_items
        if item.attention_class == "waiting_on_external"
    )
    recent_boundary = datetime.now(timezone.utc) - timedelta(days=1)
    completed_recently = tuple(
        item
        for item in milestone_items
        if item.status == "completed"
        and item.completed_at is not None
        and item.completed_at >= recent_boundary
    )
    return RoadmapPage(
        roadmaps=roadmap_items,
        milestones=milestone_items,
        waiting_for_me=actionable,
        owner_attention=actionable,
        running_milestones=running_items,
        dependency_waiting_milestones=dependency_items,
        capacity_waiting_milestones=capacity_items,
        external_work_milestones=external_items,
        completed_recently=completed_recently,
        current_milestones=tuple(item_by_id[item.id] for item in current),
        next_approved_milestones=tuple(item_by_id[item.id] for item in next_approved),
        future_milestones=tuple(item_by_id[item.id] for item in future),
        completed_milestones=tuple(item_by_id[item.id] for item in completed),
        blocked_milestones=tuple(item_by_id[item.id] for item in blocked),
        actionable_count=len(actionable),
        projection_warnings=roadmap_warnings + milestone_warnings,
    )


@router.post(
    "/milestones/{milestone_id}/actions",
    response_model=MilestoneItem,
    summary="Apply one versioned owner milestone action",
)
async def act_on_milestone(
    milestone_id: UUID,
    request: MilestoneActionRequest,
    context: ApproveContext,
    session: DatabaseSession,
) -> MilestoneItem:
    try:
        item = await external_adoption_service.owner_action(
            session,
            context=context,
            milestone_id=milestone_id,
            action=request.action,
            expected_version=request.expected_version,
            reason=request.reason,
        )
        if item is None:
            item = await roadmap_service.action(
                session,
                context=context,
                milestone_id=milestone_id,
                action=request.action,
                expected_version=request.expected_version,
                reason=request.reason,
            )
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error
    return MilestoneItem.model_validate(item)


@router.post(
    "/milestones/{milestone_id}/external-adoptions",
    response_model=ExternalAdoptionItem,
    status_code=status.HTTP_201_CREATED,
    summary="Adopt one eligible external milestone without dispatching it",
)
async def adopt_external_milestone(
    milestone_id: UUID,
    request: ExternalAdoptionCreate,
    context: ManageContext,
    session: DatabaseSession,
) -> ExternalAdoptionItem:
    try:
        adoption = await external_adoption_service.adopt(
            session,
            context=context,
            milestone_id=milestone_id,
            payload=request,
        )
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ExternalAdoptionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return ExternalAdoptionItem.model_validate(adoption)


@router.post(
    "/external-adoptions/{adoption_id}/evidence",
    response_model=ExternalAdoptionItem,
    summary="Append authenticated bounded external workstream evidence",
)
async def handoff_external_evidence(
    adoption_id: UUID,
    request: ExternalEvidenceCreate,
    context: ManageContext,
    session: DatabaseSession,
) -> ExternalAdoptionItem:
    try:
        await external_adoption_service.handoff(
            session,
            context=context,
            adoption_id=adoption_id,
            payload=request,
        )
        adoption = await session.get(ExternalMilestoneAdoption, adoption_id)
        assert adoption is not None
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ExternalAdoptionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return ExternalAdoptionItem.model_validate(adoption)


@router.get(
    "/notifications",
    response_model=MissionNotificationPage,
    summary="List persisted Mission Control notifications",
)
async def list_mission_notifications(
    context: ReadContext,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> MissionNotificationPage:
    records, total = await mission_notification_service.list(
        session, context=context, page=page, page_size=page_size
    )
    items = tuple(MissionNotificationItem.model_validate(item) for item in records)
    return MissionNotificationPage(
        items=items,
        unread_count=sum(item.status == "unread" for item in records),
        escalated_count=sum(
            item.status == "unread" and item.escalated_at is not None
            for item in records
        ),
        page=page,
        page_size=page_size,
        total_count=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post(
    "/notifications/{notification_id}/acknowledge",
    response_model=MissionNotificationItem,
    summary="Acknowledge one Mission Control notification",
)
async def acknowledge_mission_notification(
    notification_id: UUID,
    request: MissionNotificationAcknowledgement,
    context: ManageContext,
    session: DatabaseSession,
) -> MissionNotificationItem:
    try:
        record = await mission_notification_service.acknowledge(
            session,
            context=context,
            notification_id=notification_id,
            expected_version=request.expected_version,
        )
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return MissionNotificationItem.model_validate(record)


@router.post(
    "/notifications/{notification_id}/transition",
    response_model=MissionNotificationItem,
    summary="Mark a Mission Control notification read or archived",
)
async def transition_mission_notification(
    notification_id: UUID,
    request: MissionNotificationTransition,
    context: ManageContext,
    session: DatabaseSession,
) -> MissionNotificationItem:
    try:
        record = await mission_notification_service.transition(
            session,
            context=context,
            notification_id=notification_id,
            expected_version=request.expected_version,
            action=request.action,
        )
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return MissionNotificationItem.model_validate(record)


@router.get(
    "/events",
    summary="Stream ordered authoritative Engineering runtime events",
    response_class=StreamingResponse,
)
async def stream_workstream_events(
    context: ReadContext,
    session: DatabaseSession,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: UUID | None = None,
) -> StreamingResponse:
    try:
        header_token = UUID(last_event_id) if last_event_id else None
    except ValueError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid Last-Event-ID."
        ) from error
    if header_token and after and header_token != after:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Conflicting realtime resume tokens."
        )
    token = header_token or after
    try:
        await validate_resume_token(session, context.company.id, token)
    except InvalidResumeToken as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    finally:
        # Release the request-scoped database connection before the stream's
        # intentionally long lifetime. Replays use short independent sessions.
        await session.rollback()
    return StreamingResponse(
        event_stream(context.company.id, token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/workstreams",
    response_model=MobileWorkstreamPage,
    summary="List authoritative Engineering workstreams",
)
async def list_workstreams(
    context: ReadContext,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> MobileWorkstreamPage:
    return await mobile_engineering_control_service.list_workstreams(
        session,
        context=context,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/workstreams/{command_id}",
    response_model=MobileWorkstreamDetail,
    summary="Get an authoritative Engineering workstream",
)
async def get_workstream(
    command_id: UUID, context: ReadContext, session: DatabaseSession
) -> MobileWorkstreamDetail:
    try:
        return await mobile_engineering_control_service.workstream_detail(
            session, context=context, command_id=command_id
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error


@router.post(
    "/workstreams/{command_id}/actions",
    response_model=MobileWorkstreamActionResult,
    summary="Request an owner workstream control action",
)
async def control_workstream(
    command_id: UUID,
    request: MobileWorkstreamActionRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> MobileWorkstreamActionResult:
    try:
        return await mobile_engineering_control_service.control_workstream(
            session,
            context=context,
            command_id=command_id,
            action=request.action,
            reason=request.reason,
        )
    except ValueError as error:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error


@router.get(
    "/owner-reviews",
    response_model=MobileOwnerReviewPage,
    summary="List immutable completed-result owner reviews",
)
async def list_owner_reviews(
    context: ReadContext,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> MobileOwnerReviewPage:
    return await mobile_engineering_control_service.list_owner_reviews(
        session,
        context=context,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/reviews",
    response_model=MobileCommandPage,
    summary="List pending owner reviews",
)
async def list_pending_reviews(
    context: ReadContext,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> MobileCommandPage:
    try:
        return await mobile_engineering_control_service.list_pending(
            session, context=context, page=page, page_size=page_size
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error


@router.get(
    "/reviews/{command_id}",
    response_model=MobileCommandDetail,
    summary="Read an owner review item",
)
@router.get(
    "/commands/{command_id}/status",
    response_model=MobileCommandDetail,
    summary="Read command status",
)
async def get_mobile_command(
    command_id: UUID, context: ReadContext, session: DatabaseSession
) -> MobileCommandDetail:
    try:
        return await mobile_engineering_control_service.detail(
            session, context=context, command_id=command_id
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error


@router.post(
    "/reviews/{command_id}/approve",
    response_model=MobileCommandDetail,
    summary="Approve reviewed evidence without starting execution",
    description=(
        "Approves the exact Engineering Command evidence only. No worker, provider, "
        "repository operation, or execution is started."
    ),
)
async def approve_mobile_command(
    command_id: UUID,
    data: MobileApprovalRequest,
    context: ApproveContext,
    session: DatabaseSession,
) -> MobileCommandDetail:
    try:
        return await mobile_engineering_control_service.approve(
            session,
            context=context,
            command=ApproveEngineeringCommand(
                command_id=command_id, **data.model_dump()
            ),
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error


@router.post(
    "/reviews/{command_id}/cancel",
    response_model=MobileCommandDetail,
    summary="Cancel an eligible owner review",
)
async def cancel_mobile_command(
    command_id: UUID,
    data: MobileCancellationRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> MobileCommandDetail:
    try:
        return await mobile_engineering_control_service.cancel(
            session,
            context=context,
            command=CancelEngineeringCommand(
                command_id=command_id, **data.model_dump()
            ),
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error
