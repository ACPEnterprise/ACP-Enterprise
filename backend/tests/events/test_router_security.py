from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.config import settings
from app.database.session import (
    get_database_session,
    get_security_database_session,
)
from app.events.models import BusinessEvent
from app.events.router import router
from app.events.service import BusinessEventService


@pytest_asyncio.fixture
async def event_database() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_event_http_boundary_requires_authentication_and_has_no_publish_route() -> None:
    application = FastAPI()
    application.include_router(router)

    async def no_database():
        yield None

    application.dependency_overrides[get_database_session] = no_database
    application.dependency_overrides[get_security_database_session] = no_database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        listed = await client.get("/api/v1/events")
        latest = await client.get("/api/v1/events/latest")
        published = await client.post(
            "/api/v1/events",
            json={"event_type": "system.started", "entity_type": "synthetic"},
        )

    assert listed.status_code == 401
    assert latest.status_code == 401
    assert published.status_code == 405


@pytest.mark.asyncio
async def test_event_reads_are_company_and_authorized_branch_scoped(
    event_database: AsyncEngine,
) -> None:
    company_id = uuid4()
    other_company_id = uuid4()
    allowed_branch = uuid4()
    denied_branch = uuid4()
    async with AsyncSession(event_database) as session, session.begin():
        session.add_all(
            [
                BusinessEvent(
                    event_type="system.started",
                    entity_type="company",
                    company_id=company_id,
                    branch_id=None,
                    payload={"scope": "company"},
                ),
                BusinessEvent(
                    event_type="system.started",
                    entity_type="branch",
                    company_id=company_id,
                    branch_id=allowed_branch,
                    payload={"scope": "allowed"},
                ),
                BusinessEvent(
                    event_type="system.started",
                    entity_type="branch",
                    company_id=company_id,
                    branch_id=denied_branch,
                    payload={"scope": "denied"},
                ),
                BusinessEvent(
                    event_type="system.started",
                    entity_type="company",
                    company_id=other_company_id,
                    branch_id=None,
                    payload={"scope": "foreign"},
                ),
            ]
        )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        membership=SimpleNamespace(has_all_branch_access=False),
        authorized_branch_ids=frozenset({allowed_branch}),
    )

    async with AsyncSession(event_database) as session:
        records = await BusinessEventService.list_events(
            session,
            context=context,  # type: ignore[arg-type]
            limit=50,
            offset=0,
        )
        latest = await BusinessEventService.latest_events(
            session,
            context=context,  # type: ignore[arg-type]
            limit=10,
        )

    assert {record.payload["scope"] for record in records} == {"company", "allowed"}
    assert {record.payload["scope"] for record in latest} == {"company", "allowed"}
