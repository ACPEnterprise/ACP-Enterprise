from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
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
async def lifecycle_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_customer_archive_restore_events_and_idempotency(
    lifecycle_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = lifecycle_database
    fixture = await seed_customer_fixture(factory, "LIFECYCLE")
    app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/customers",
            json={"customer_type": "hoa", "display_name": "Lifecycle Customer"},
        )
        customer_id = created.json()["id"]

        archived = await client.post(f"/api/v1/customers/{customer_id}/archive")
        assert archived.status_code == 200, archived.text
        assert archived.json()["archived"] is True
        assert archived.json()["archived_at"] is not None
        hidden = await client.get(f"/api/v1/customers/{customer_id}")
        assert hidden.status_code == 404

        repeated_archive = await client.post(f"/api/v1/customers/{customer_id}/archive")
        assert repeated_archive.status_code == 200
        assert repeated_archive.json() == archived.json()

        restored = await client.post(f"/api/v1/customers/{customer_id}/restore")
        assert restored.status_code == 200, restored.text
        assert restored.json()["archived"] is False
        assert restored.json()["archived_at"] is None
        visible = await client.get(f"/api/v1/customers/{customer_id}")
        assert visible.status_code == 200

        repeated_restore = await client.post(f"/api/v1/customers/{customer_id}/restore")
        assert repeated_restore.status_code == 200
        assert repeated_restore.json() == restored.json()

    async with factory() as session:
        event_rows = (
            await session.execute(
                select(BusinessEvent.event_type, func.count())
                .where(
                    BusinessEvent.entity_id == UUID(customer_id),
                    BusinessEvent.event_type.in_(
                        ["customer.archived", "customer.restored"]
                    ),
                )
                .group_by(BusinessEvent.event_type)
            )
        ).all()
        event_counts: dict[str, int] = {
            event_type: count for event_type, count in event_rows
        }
        record = await session.scalar(
            select(Customer).where(Customer.id == UUID(customer_id))
        )
    assert event_counts == {"customer.archived": 1, "customer.restored": 1}
    assert record is not None and record.archived_at is None


@pytest.mark.asyncio
async def test_customer_lifecycle_is_company_and_permission_scoped(
    lifecycle_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = lifecycle_database
    fixture = await seed_customer_fixture(factory, "LIFECYCLEISO")
    owner_app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/customers",
            json={"customer_type": "municipal", "display_name": "Private Customer"},
        )
    customer_id = created.json()["id"]

    other_app = build_app(factory, fixture.other_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=other_app), base_url="http://test"
    ) as client:
        hidden_archive = await client.post(f"/api/v1/customers/{customer_id}/archive")
        hidden_restore = await client.post(f"/api/v1/customers/{customer_id}/restore")
    assert hidden_archive.status_code == 404
    assert hidden_restore.status_code == 404

    restricted_app = build_app(factory, fixture.restricted_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restricted_app), base_url="http://test"
    ) as client:
        denied = await client.post(f"/api/v1/customers/{customer_id}/archive")
    assert denied.status_code == 403
