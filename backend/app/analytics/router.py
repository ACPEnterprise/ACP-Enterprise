from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import AnalyticsSummaryResponse
from app.analytics.service import AnalyticsService
from app.database.session import get_database_session


router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Analytics"],
)

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_database_session),
]


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
)
async def get_analytics_summary(
    session: DatabaseSession,
    recent_limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> AnalyticsSummaryResponse:
    return await AnalyticsService.get_today_summary(
        session=session,
        recent_limit=recent_limit,
    )
