from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import (
    AnalyticsDrilldownResponse,
    AnalyticsMetricKey,
    AnalyticsSummaryResponse,
    RevenueTrendResponse,
)
from app.analytics.service import AnalyticsService
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AnalyticsPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Analytics"],
)

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_database_session),
]
AnalyticsReader = Annotated[
    AuthorizationContext,
    Depends(require_permission(AnalyticsPermission.READ)),
]


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
)
async def get_analytics_summary(
    session: DatabaseSession,
    authorization: AnalyticsReader,
    recent_limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> AnalyticsSummaryResponse:
    return await AnalyticsService.get_today_summary(
        session=session,
        company_id=authorization.company.id,
        recent_limit=recent_limit,
    )


@router.get(
    "/revenue-trend",
    response_model=RevenueTrendResponse,
)
async def get_revenue_trend(
    session: DatabaseSession,
    authorization: AnalyticsReader,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> RevenueTrendResponse:
    return await AnalyticsService.get_revenue_trend(
        session=session,
        company_id=authorization.company.id,
        days=days,
    )


@router.get(
    "/metric-detail",
    response_model=AnalyticsDrilldownResponse,
)
async def get_metric_detail(
    session: DatabaseSession,
    authorization: AnalyticsReader,
    metric: AnalyticsMetricKey,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> AnalyticsDrilldownResponse:
    try:
        return await AnalyticsService.get_metric_detail(
            session=session,
            company_id=authorization.company.id,
            company_name=authorization.company.name,
            metric=metric,
            period_start=period_start,
            period_end=period_end,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
