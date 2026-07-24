from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import require_permission

from .schemas import MobileExecutionStatus
from .service import (
    ExecutionStatusNotFoundError,
    mobile_execution_status_service,
)


router = APIRouter(
    prefix="/api/v1/engineering/mobile",
    tags=["Mobile Engineering Execution Status"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.READ)),
]


@router.get(
    "/commands/{command_id}/execution-status",
    response_model=MobileExecutionStatus,
    summary="Read authoritative execution monitoring status",
    description=(
        "Returns a read-only, Company-scoped status projection. Missing fields are "
        "reported explicitly and no execution, worker, or repository action occurs."
    ),
)
async def get_execution_status(
    command_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> MobileExecutionStatus:
    try:
        return await mobile_execution_status_service.get(
            session, context=context, command_id=command_id
        )
    except ExecutionStatusNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engineering Command not found.",
        ) from error
