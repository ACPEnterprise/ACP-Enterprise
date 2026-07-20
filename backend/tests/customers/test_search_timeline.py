from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.events.models import BusinessEvent
from tests.customers.test_api import build_app, seed_customer_fixture


@pytest_asyncio.fixture
async def search_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def create_search_records(client: httpx.AsyncClient) -> tuple[dict, dict]:
    acme_response = await client.post(
        "/api/v1/customers",
        json={
            "customer_type": "commercial",
            "display_name": "Acme Plumbing Portfolio",
            "legal_name": "Acme Holdings LLC",
            "status": "active",
        },
    )
    assert acme_response.status_code == 201, acme_response.text
    acme = acme_response.json()
    contact = await client.post(
        f"/api/v1/customers/{acme['id']}/contacts",
        json={
            "first_name": "Marisol",
            "last_name": "Quintero",
            "email": "Dispatch.Team@Example.COM",
            "mobile_phone": "(727) 555-0198",
            "office_phone": "727-555-0107",
            "is_preferred": True,
        },
    )
    assert contact.status_code == 201, contact.text
    location = await client.post(
        f"/api/v1/customers/{acme['id']}/locations",
        json={
            "address": "880 Enterprise Boulevard",
            "city": "Clearwater",
            "state": "Florida",
            "postal_code": "33755",
        },
    )
    assert location.status_code == 201, location.text

    prospect_response = await client.post(
        "/api/v1/customers",
        json={
            "customer_type": "residential",
            "display_name": "Zelda North",
            "status": "prospect",
        },
    )
    assert prospect_response.status_code == 201, prospect_response.text
    return acme, prospect_response.json()


@pytest.mark.asyncio
async def test_enterprise_customer_search_filter_sort_and_pagination(
    search_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = search_database
    fixture = await seed_customer_fixture(factory, "SEARCH")
    app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        acme, prospect = await create_search_records(client)

        searches = {
            acme["customer_number"][-4:]: acme["id"],
            "plumbing port": acme["id"],
            "holdings llc": acme["id"],
            "marisol quint": acme["id"],
            "DISPATCH.TEAM@example.com": acme["id"],
            "5550198": acme["id"],
            "555-0107": acme["id"],
            "enterprise boule": acme["id"],
            "clearWATER": acme["id"],
            "33755": acme["id"],
        }
        for query, expected_id in searches.items():
            response = await client.get(
                "/api/v1/customers/search", params={"query": query}
            )
            assert response.status_code == 200, response.text
            assert expected_id in {item["id"] for item in response.json()["items"]}

        filtered = await client.get(
            "/api/v1/customers/search",
            params={
                "status": "active",
                "customer_type": "commercial",
                "has_preferred_contact": "true",
                "has_active_service_locations": "true",
                "created_from": acme["created_at"],
                "updated_to": (
                    datetime.now(timezone.utc) + timedelta(minutes=1)
                ).isoformat(),
            },
        )
        assert filtered.status_code == 200, filtered.text
        assert [item["id"] for item in filtered.json()["items"]] == [acme["id"]]

        page = await client.get(
            "/api/v1/customers/search",
            params={
                "page": 1,
                "page_size": 1,
                "sort_by": "display_name",
                "sort_direction": "desc",
            },
        )
        assert page.status_code == 200, page.text
        body = page.json()
        assert body == {
            **body,
            "page": 1,
            "page_size": 1,
            "total_count": 2,
            "total_pages": 2,
        }
        assert body["items"][0]["id"] == prospect["id"]


@pytest.mark.asyncio
async def test_customer_search_and_timeline_are_tenant_and_permission_scoped(
    search_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = search_database
    fixture = await seed_customer_fixture(factory, "TIMELINE")
    app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        customer, _ = await create_search_records(client)
        status_response = await client.patch(
            f"/api/v1/customers/{customer['id']}/status",
            json={"status": "inactive"},
        )
        assert status_response.status_code == 200

    newest_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    async with factory() as session, session.begin():
        session.add(
            BusinessEvent(
                event_type="authentication.customer_access_reviewed",
                entity_type="access_review",
                entity_id=uuid4(),
                company_id=fixture.context.company.id,
                user_id=fixture.context.user.id,
                payload={
                    "customer_id": customer["id"],
                    "status": "reviewed",
                    "token": "must-not-escape",
                    "email": "private@example.com",
                },
                occurred_at=newest_at,
            )
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/v1/customers/{customer['id']}/timeline",
            params={"page": 1, "page_size": 3},
        )
    assert response.status_code == 200, response.text
    timeline = response.json()
    assert timeline["page"] == 1
    assert timeline["page_size"] == 3
    assert timeline["total_count"] >= 5
    assert timeline["total_pages"] >= 2
    timestamps = [item["timestamp"] for item in timeline["items"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert (
        timeline["items"][0]["event_type"] == "authentication.customer_access_reviewed"
    )
    assert timeline["items"][0]["summary"] == "Customer access authentication event"
    assert timeline["items"][0]["actor"]["id"] == str(fixture.context.user.id)
    assert timeline["items"][0]["metadata"] == {
        "customer_id": customer["id"],
        "status": "reviewed",
    }
    assert any(
        item["summary"] == "Status changed to Inactive" for item in timeline["items"]
    )

    other_app = build_app(factory, fixture.other_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=other_app), base_url="http://test"
    ) as client:
        search = await client.get("/api/v1/customers/search", params={"query": "Acme"})
        hidden = await client.get(f"/api/v1/customers/{customer['id']}/timeline")
    assert search.status_code == 200
    assert search.json()["total_count"] == 0
    assert hidden.status_code == 404

    restricted_app = build_app(factory, fixture.restricted_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restricted_app), base_url="http://test"
    ) as client:
        denied_search = await client.get("/api/v1/customers/search")
        denied_timeline = await client.get(
            f"/api/v1/customers/{UUID(customer['id'])}/timeline"
        )
    assert denied_search.status_code == 403
    assert denied_timeline.status_code == 403
