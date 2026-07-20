from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.customers.models import Customer
from app.events.models import BusinessEvent
from tests.customers.test_api import build_app, seed_customer_fixture


@pytest_asyncio.fixture
async def update_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_customer_update_service_contract_events_and_idempotency(
    update_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = update_database
    fixture = await seed_customer_fixture(factory, "UPDATE")
    app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/customers",
            json={"customer_type": "residential", "display_name": "Original Name"},
        )
        customer = created.json()
        response = await client.patch(
            f"/api/v1/customers/{customer['id']}",
            json={
                "display_name": "Updated Name",
                "legal_name": "Updated Legal Name LLC",
                "status": "active",
                "customer_type": "commercial",
                "preferred_contact_method": "email",
            },
        )
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["display_name"] == "Updated Name"
        assert updated["legal_name"] == "Updated Legal Name LLC"
        assert updated["status"] == "active"
        assert updated["customer_type"] == "commercial"
        assert updated["preferred_contact_method"] == "email"
        assert "active_service_locations" in updated

        unchanged = await client.patch(
            f"/api/v1/customers/{customer['id']}",
            json={"display_name": "Updated Name", "status": "active"},
        )
        assert unchanged.status_code == 200
        assert unchanged.json()["updated_at"] == updated["updated_at"]

        unknown = await client.patch(
            f"/api/v1/customers/{customer['id']}", json={"notes": "not allowed"}
        )
        assert unknown.status_code == 422

    async with factory() as session:
        events = list(
            (
                await session.scalars(
                    select(BusinessEvent)
                    .where(
                        BusinessEvent.entity_id == UUID(customer["id"]),
                        BusinessEvent.event_type.in_(
                            ["customer.updated", "customer.status_changed"]
                        ),
                    )
                    .order_by(BusinessEvent.occurred_at)
                )
            ).all()
        )
    assert [event.event_type for event in events] == [
        "customer.updated",
        "customer.status_changed",
    ]
    assert events[0].payload["changed_fields"] == [
        "customer_type",
        "display_name",
        "legal_name",
        "preferred_contact_method",
        "status",
    ]


@pytest.mark.asyncio
async def test_customer_update_transition_tenant_and_archive_guards(
    update_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = update_database
    fixture = await seed_customer_fixture(factory, "UPDATEGUARD")
    owner_app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/customers",
            json={
                "customer_type": "municipal",
                "display_name": "City Utilities",
                "status": "active",
            },
        )
        customer_id = created.json()["id"]
        prohibited = await client.patch(
            f"/api/v1/customers/{customer_id}", json={"status": "prospect"}
        )
    assert prohibited.status_code == 409
    assert prohibited.json() == {
        "detail": "The requested Customer status transition is not allowed."
    }

    other_app = build_app(factory, fixture.other_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=other_app), base_url="http://test"
    ) as client:
        hidden = await client.patch(
            f"/api/v1/customers/{customer_id}", json={"display_name": "Leaked"}
        )
    assert hidden.status_code == 404

    async with factory() as session, session.begin():
        record = await session.scalar(
            select(Customer).where(Customer.id == UUID(customer_id)).with_for_update()
        )
        assert record is not None
        record.archived_at = datetime.now(timezone.utc)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app), base_url="http://test"
    ) as client:
        archived = await client.patch(
            f"/api/v1/customers/{customer_id}", json={"display_name": "Archived"}
        )
    assert archived.status_code == 404
