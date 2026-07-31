from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CancelEngineeringCommand,
)
from app.engineering_control.errors import EngineeringControlError
from app.engineering_control.http_errors import engineering_http_error
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import require_permission

from .notifications import mission_notification_service
from .realtime import InvalidResumeToken, event_stream, validate_resume_token
from .roadmaps import roadmap_service
from .schemas import (
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
    actionable = tuple(
        item for item in milestones if item.status in roadmap_service.actionable
    )
    current = tuple(
        item
        for item in milestones
        if item.status in {"ready", "running", "paused", "waiting_review"}
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
        if item.status == "planned" and item.id not in next_ids
    )
    completed = tuple(item for item in milestones if item.status == "completed")
    blocked = tuple(item for item in milestones if item.status == "blocked")
    return RoadmapPage(
        roadmaps=tuple(RoadmapItem.model_validate(item) for item in roadmaps),
        milestones=tuple(MilestoneItem.model_validate(item) for item in milestones),
        waiting_for_me=tuple(MilestoneItem.model_validate(item) for item in actionable),
        current_milestones=tuple(
            MilestoneItem.model_validate(item) for item in current
        ),
        next_approved_milestones=tuple(
            MilestoneItem.model_validate(item) for item in next_approved
        ),
        future_milestones=tuple(MilestoneItem.model_validate(item) for item in future),
        completed_milestones=tuple(
            MilestoneItem.model_validate(item) for item in completed
        ),
        blocked_milestones=tuple(
            MilestoneItem.model_validate(item) for item in blocked
        ),
        actionable_count=len(actionable),
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
    return MilestoneItem.model_validate(item)


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
