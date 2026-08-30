from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.events.schemas import BusinessEventResponse
from app.events.service import BusinessEventService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import LaunchPlatformPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(
    prefix="/api/v1/events",
    tags=["Business Events"],
)

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_database_session),
]
EventReader = Annotated[
    AuthorizationContext,
    Depends(require_permission(LaunchPlatformPermission.AUDIT_READ)),
]


@router.get(
    "",
    response_model=list[BusinessEventResponse],
)
async def list_events(
    context: EventReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BusinessEventResponse]:
    events = await BusinessEventService.list_events(
        session=session,
        context=context,
        limit=limit,
        offset=offset,
    )

    return [BusinessEventResponse.model_validate(event) for event in events]


@router.get(
    "/latest",
    response_model=list[BusinessEventResponse],
)
async def latest_events(
    context: EventReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[BusinessEventResponse]:
    events = await BusinessEventService.latest_events(
        session=session,
        context=context,
        limit=limit,
    )

    return [BusinessEventResponse.model_validate(event) for event in events]
