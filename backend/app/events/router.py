from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.events.schemas import (
    BusinessEventCreate,
    BusinessEventResponse,
)
from app.events.service import BusinessEventService


router = APIRouter(
    prefix="/api/v1/events",
    tags=["Business Events"],
)

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_database_session),
]


@router.post(
    "",
    response_model=BusinessEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_event(
    event_data: BusinessEventCreate,
    session: DatabaseSession,
) -> BusinessEventResponse:
    event = await BusinessEventService.publish(
        session=session,
        event_data=event_data,
    )

    return BusinessEventResponse.model_validate(event)


@router.get(
    "",
    response_model=list[BusinessEventResponse],
)
async def list_events(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BusinessEventResponse]:
    events = await BusinessEventService.list_events(
        session=session,
        limit=limit,
        offset=offset,
    )

    return [
        BusinessEventResponse.model_validate(event)
        for event in events
    ]


@router.get(
    "/latest",
    response_model=list[BusinessEventResponse],
)
async def latest_events(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[BusinessEventResponse]:
    events = await BusinessEventService.latest_events(
        session=session,
        limit=limit,
    )

    return [
        BusinessEventResponse.model_validate(event)
        for event in events
    ]
