from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CommunicationsPermission
from app.platform.permissions.dependencies import require_permission

from .contracts import CommunicationRequest
from .errors import (
    CommunicationAuthorizationError,
    CommunicationConflictError,
    CommunicationError,
    CommunicationNotFoundError,
    CommunicationValidationError,
)
from .schemas import CommunicationCreate, CommunicationItem, CommunicationPage
from .service import communication_service

router = APIRouter(prefix="/api/v1/communications", tags=["Communications"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(CommunicationsPermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(CommunicationsPermission.MANAGE))
]


def communication_http(error: CommunicationError) -> HTTPException:
    if isinstance(error, CommunicationAuthorizationError):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    if isinstance(error, CommunicationNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, CommunicationConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, CommunicationValidationError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Communication operation failed.")


@router.post("/requests", response_model=CommunicationItem, status_code=201)
async def create_request(
    payload: CommunicationCreate,
    context: ManageContext,
    session: DatabaseSession,
) -> CommunicationItem:
    try:
        evidence = await communication_service.request(
            session,
            context=context,
            request=CommunicationRequest(**payload.model_dump()),
        )
        return CommunicationItem.model_validate(evidence)
    except CommunicationError as error:
        raise communication_http(error) from error


@router.get("/history", response_model=CommunicationPage)
async def history(
    context: ReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CommunicationPage:
    try:
        items = await communication_service.list(
            session,
            context=context,
            branch_id=branch_id,
            limit=limit,
        )
        return CommunicationPage(
            items=tuple(CommunicationItem.model_validate(item) for item in items)
        )
    except CommunicationError as error:
        raise communication_http(error) from error
