from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.economics.models import ProfitMeasurementRecord
from app.economics.service import EconomicsQueryService
from app.platform.company.models import Company


@pytest_asyncio.fixture
async def economics_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_measurement_queries_are_tenant_scoped_and_retain_evidence(
    economics_database: async_sessionmaker[AsyncSession],
) -> None:
    suffix = uuid4().hex[:8].upper()
    companies = (
        Company(
            name="Economics A", code=f"ECA{suffix}", status="active", timezone="UTC"
        ),
        Company(
            name="Economics B", code=f"ECB{suffix}", status="active", timezone="UTC"
        ),
    )
    subject_id = uuid4()
    evidence = [
        {
            "kind": "business_event",
            "reference_id": str(uuid4()),
            "source_system": "acp_enterprise",
            "source_version": "1",
            "explanation": "Payment received event.",
        },
        {
            "kind": "reasoning",
            "reference_id": "business-economics/1",
            "source_system": "business_economics",
            "source_version": "business-economics/1",
            "explanation": "Versioned profit formula.",
        },
    ]
    async with economics_database() as session, session.begin():
        session.add_all(companies)
        await session.flush()
        for company, net_profit in zip(companies, (48_000, 99_000), strict=True):
            session.add(
                ProfitMeasurementRecord(
                    company_id=company.id,
                    subject_type="job",
                    subject_id=subject_id,
                    currency="USD",
                    revenue_minor=100_000,
                    labor_minor=20_000,
                    materials_minor=15_000,
                    equipment_minor=5_000,
                    truck_minor=2_000,
                    overhead_minor=10_000,
                    gross_profit_minor=58_000,
                    net_profit_minor=net_profit,
                    confidence_status="measured",
                    confidence_percentage=100,
                    confidence_explanation="All inputs are measured.",
                    evidence=evidence,
                    engine_version="business-economics/1",
                    version=1,
                    measured_at=datetime.now(timezone.utc),
                )
            )

    async with economics_database() as session:
        response = await EconomicsQueryService.latest_for_subject(
            session, companies[0].id, "job", subject_id
        )
        listing = await EconomicsQueryService.list_measurements(
            session, companies[0].id, limit=50, offset=0
        )

    assert response.net_profit_minor == 48_000
    assert response.company_id == companies[0].id
    assert len(response.evidence) == 2
    assert [item.id for item in listing.items] == [response.id]
