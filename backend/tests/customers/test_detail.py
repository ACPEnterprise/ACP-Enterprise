from collections.abc import AsyncIterator

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
from tests.customers.test_api import build_app, seed_customer_fixture


@pytest_asyncio.fixture
async def detail_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_customer_detail_returns_complete_partitioned_read_model(
    detail_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = detail_database
    fixture = await seed_customer_fixture(factory, "DETAIL")
    app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/customers",
            json={
                "customer_type": "property_management",
                "display_name": "Harbor Property Group",
                "status": "active",
            },
        )
        assert created.status_code == 201, created.text
        customer = created.json()

        preferred = await client.post(
            f"/api/v1/customers/{customer['id']}/contacts",
            json={
                "first_name": "Amaya",
                "last_name": "Stone",
                "email": "amaya@example.com",
                "is_preferred": True,
            },
        )
        secondary = await client.post(
            f"/api/v1/customers/{customer['id']}/contacts",
            json={"first_name": "Ben", "last_name": "Stone"},
        )
        active_location = await client.post(
            f"/api/v1/customers/{customer['id']}/locations",
            json={
                "nickname": "Office",
                "address": "10 Harbor Way",
                "city": "Clearwater",
                "state": "Florida",
                "postal_code": "33755",
            },
        )
        inactive_location = await client.post(
            f"/api/v1/customers/{customer['id']}/locations",
            json={
                "nickname": "Former Office",
                "address": "20 Harbor Way",
                "city": "Clearwater",
                "state": "Florida",
                "postal_code": "33755",
                "active": False,
            },
        )
        assert all(
            response.status_code == 201
            for response in (preferred, secondary, active_location, inactive_location)
        )

        response = await client.get(f"/api/v1/customers/{customer['id']}")

    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["id"] == customer["id"]
    assert detail["preferred_contact"]["id"] == preferred.json()["id"]
    assert {contact["id"] for contact in detail["contacts"]} == {
        preferred.json()["id"],
        secondary.json()["id"],
    }
    assert [location["id"] for location in detail["active_service_locations"]] == [
        active_location.json()["id"]
    ]
    assert [location["id"] for location in detail["inactive_service_locations"]] == [
        inactive_location.json()["id"]
    ]
    assert {location["id"] for location in detail["locations"]} == {
        active_location.json()["id"],
        inactive_location.json()["id"],
    }
    assert detail["metadata"] == {
        "company_id": str(fixture.context.company.id),
        "customer_number": customer["customer_number"],
        "status": "active",
        "customer_type": "property_management",
        "preferred_contact_method": "phone",
        "created_at": detail["created_at"],
        "updated_at": detail["updated_at"],
    }


@pytest.mark.asyncio
async def test_customer_detail_is_company_scoped_and_returns_not_found(
    detail_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = detail_database
    fixture = await seed_customer_fixture(factory, "DETAILISO")
    owner_app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/customers",
            json={"customer_type": "hoa", "display_name": "Hidden Customer"},
        )
    customer_id = created.json()["id"]

    other_app = build_app(factory, fixture.other_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=other_app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/customers/{customer_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Customer resource was not found."}
