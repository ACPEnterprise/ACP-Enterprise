from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
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

from .schemas import (
    MobileApprovalRequest,
    MobileCancellationRequest,
    MobileCommandDetail,
    MobileCommandPage,
    MobileOwnerReviewPage,
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
