from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringExecutionPermission
from app.platform.permissions.dependencies import require_permission

from .errors import ControlledExecutionError
from .schemas import ControlledOfferResponse, PrepareControlledOfferRequest
from .service import ControlledExecutionService

router = APIRouter(
    prefix="/api/v1/engineering-executions",
    tags=["Controlled Engineering Execution"],
)
Database = Annotated[AsyncSession, Depends(get_database_session)]
ExecutionContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringExecutionPermission.REQUEST)),
]
service = ControlledExecutionService()


@router.post(
    "/{execution_id}/controlled-offers",
    response_model=ControlledOfferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Prepare one immutable read-only controlled execution offer",
)
async def prepare_controlled_offer(
    execution_id: UUID,
    data: PrepareControlledOfferRequest,
    context: ExecutionContext,
    database: Database,
) -> ControlledOfferResponse:
    try:
        offer = await service.prepare_offer(
            database,
            context=context,
            execution_id=execution_id,
            workspace_id=data.workspace_id,
            lease_seconds=data.lease_seconds,
        )
    except ControlledExecutionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "controlled_execution_ineligible"},
        ) from error
    return ControlledOfferResponse(
        id=offer.id,
        command_id=offer.command_id,
        execution_id=offer.execution_id,
        workspace_id=offer.workspace_id,
        command_type=offer.command_type.value,
        capability_required=offer.capability_required.value,
        state=offer.state.value,
        expires_at=offer.expires_at,
        lease_seconds=offer.lease_seconds,
        created_at=offer.created_at,
    )
