from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.analytics.service import AnalyticsService
from app.core.config import settings
from tests.analytics.test_analytics import (
    build_app,
    seed_analytics_fixture,
    seed_events,
)


@pytest_asyncio.fixture
async def revenue_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_revenue_trend_bucketing_precision_and_tenant_isolation(
    revenue_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = revenue_database
    fixture = await seed_analytics_fixture(factory)
    await seed_events(factory, fixture)
    async with factory() as session:
        trend = await AnalyticsService.get_revenue_trend(
            session,
            company_id=fixture.company_a_id,
            days=7,
        )
        other_trend = await AnalyticsService.get_revenue_trend(
            session,
            company_id=fixture.company_b_id,
            days=7,
        )

    assert len(trend.points) == 7
    assert [point.date for point in trend.points] == sorted(
        point.date for point in trend.points
    )
    assert sum((point.cash_collected for point in trend.points), Decimal()) == Decimal(
        "10.10"
    )
    assert sum((point.booked_revenue for point in trend.points), Decimal()) == Decimal(
        "50.50"
    )
    assert sum(point.payment_event_count for point in trend.points) == 1
    assert sum(point.booked_event_count for point in trend.points) == 2
    assert any(
        point.cash_collected == Decimal("0.00")
        and point.booked_revenue == Decimal("0.00")
        for point in trend.points
    )
    assert sum(
        (point.cash_collected for point in other_trend.points), Decimal()
    ) == Decimal("999999.99")
    assert sum(
        (point.booked_revenue for point in other_trend.points), Decimal()
    ) == Decimal("888888.88")


@pytest.mark.asyncio
async def test_revenue_trend_api_response_shape(
    revenue_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = revenue_database
    fixture = await seed_analytics_fixture(factory)
    await seed_events(factory, fixture)
    app = build_app(factory, fixture.authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/analytics/revenue-trend?days=7",
            headers={"X-Company-ID": str(fixture.company_a_id)},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 7
    assert payload["timezone"] == settings.business_timezone
    assert len(payload["points"]) == 7
    assert set(payload["points"][0]) == {
        "date",
        "booked_revenue",
        "cash_collected",
        "booked_event_count",
        "payment_event_count",
    }
