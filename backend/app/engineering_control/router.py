from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CancelEngineeringCommand,
    CreateEngineeringCommand,
    EngineeringCommandQuery,
)
from app.engineering_control.errors import EngineeringControlError
from app.engineering_control.http_errors import engineering_http_error
from app.engineering_control.records import EngineeringApprovalState
from app.engineering_control.schemas import (
    EngineeringCommandApproveRequest,
    EngineeringCommandCancelRequest,
    EngineeringCommandCreateRequest,
    EngineeringCommandDetailResponse,
    EngineeringCommandPageResponse,
    EngineeringCommandSummaryResponse,
)
from app.engineering_control.service import EngineeringControlService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/engineering-commands", tags=["Engineering Commands"])
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
service = EngineeringControlService()


@router.get(
    "",
    response_model=EngineeringCommandPageResponse,
    summary="List Engineering Commands",
)
async def list_engineering_commands(
    context: ReadContext,
    session: DatabaseSession,
    approval_state: Annotated[EngineeringApprovalState | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> EngineeringCommandPageResponse:
    try:
        result = await service.list_commands(
            session,
            context=context,
            query=EngineeringCommandQuery(
                approval_state=approval_state, page=page, page_size=page_size
            ),
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error
    return EngineeringCommandPageResponse(
        items=tuple(
            EngineeringCommandSummaryResponse.model_validate(item)
            for item in result.items
        ),
        page=result.page,
        page_size=result.page_size,
        total_count=result.total_count,
        total_pages=result.total_pages,
    )


@router.get(
    "/{command_id}",
    response_model=EngineeringCommandDetailResponse,
    summary="Review an Engineering Command",
)
async def get_engineering_command(
    command_id: UUID, context: ReadContext, session: DatabaseSession
) -> EngineeringCommandDetailResponse:
    try:
        record = await service.get_command(
            session, context=context, command_id=command_id
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error
    return EngineeringCommandDetailResponse.model_validate(record)


@router.post(
    "",
    response_model=EngineeringCommandDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an Engineering Command",
)
async def create_engineering_command(
    data: EngineeringCommandCreateRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> EngineeringCommandDetailResponse:
    try:
        record = await service.create_command(
            session,
            context=context,
            command=CreateEngineeringCommand(**data.model_dump()),
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error
    return EngineeringCommandDetailResponse.model_validate(record)


@router.post(
    "/{command_id}/approve",
    response_model=EngineeringCommandDetailResponse,
    summary="Approve an Engineering Command without starting execution",
    description=(
        "Approves the exact reviewed command record only. This does not start "
        "Codex or any worker; execution remains execution_not_connected."
    ),
)
async def approve_engineering_command(
    command_id: UUID,
    data: EngineeringCommandApproveRequest,
    context: ApproveContext,
    session: DatabaseSession,
) -> EngineeringCommandDetailResponse:
    try:
        record = await service.approve_command(
            session,
            context=context,
            command=ApproveEngineeringCommand(
                command_id=command_id, **data.model_dump()
            ),
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error
    return EngineeringCommandDetailResponse.model_validate(record)


@router.post(
    "/{command_id}/cancel",
    response_model=EngineeringCommandDetailResponse,
    summary="Cancel an eligible Engineering Command",
)
async def cancel_engineering_command(
    command_id: UUID,
    data: EngineeringCommandCancelRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> EngineeringCommandDetailResponse:
    try:
        record = await service.cancel_command(
            session,
            context=context,
            command=CancelEngineeringCommand(
                command_id=command_id, **data.model_dump()
            ),
        )
    except EngineeringControlError as error:
        raise engineering_http_error(error) from error
    return EngineeringCommandDetailResponse.model_validate(record)
