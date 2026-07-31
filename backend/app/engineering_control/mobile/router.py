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

from .realtime import InvalidResumeToken, event_stream, validate_resume_token
from .schemas import (
    MobileApprovalRequest,
    MobileCancellationRequest,
    MobileCommandDetail,
    MobileCommandPage,
    MobileOwnerReviewPage,
    MobileWorkstreamActionRequest,
    MobileWorkstreamActionResult,
    MobileWorkstreamDetail,
    MobileWorkstreamPage,
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
