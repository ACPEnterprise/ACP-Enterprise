from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from app.core.config import settings
from app.database.session import get_database_session
from app.engineering_capacity.router import router
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCapacityPermission
from app.platform.permissions.dependencies import get_authorization_context
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
)


@pytest_asyncio.fixture
async def capacity_api_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


def app_for(fixture: ServiceFixture, permissions: tuple[str, ...]) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    context = context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        permissions,
    )

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with fixture.factory() as session:
            yield session

    async def context_override() -> AuthorizationContext:
        return context

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    return app


async def request(app: FastAPI, method: str, path: str, json=None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, json=json)


@pytest.mark.asyncio
async def test_capacity_read_and_manage_permissions_are_separate(
    capacity_api_database: ServiceFixture,
) -> None:
    fixture = capacity_api_database
    read_app = app_for(fixture, (EngineeringCapacityPermission.READ,))
    summary = await request(read_app, "GET", "/api/v1/engineering/capacity/summary")
    assert summary.status_code == 200
    assert summary.json()["policy"] is None
    denied = await request(
        read_app,
        "PUT",
        "/api/v1/engineering/capacity/policy",
        json={
            "maximum_concurrent_workstreams": 1,
            "maximum_per_worker": 1,
            "reserved_capacity": 0,
            "auto_allocate_released_capacity": False,
            "expected_version": None,
        },
    )
    assert denied.status_code == 403

    manage_app = app_for(fixture, tuple(EngineeringCapacityPermission.ALL))
    configured = await request(
        manage_app,
        "PUT",
        "/api/v1/engineering/capacity/policy",
        json={
            "maximum_concurrent_workstreams": 2,
            "maximum_per_worker": 1,
            "reserved_capacity": 0,
            "auto_allocate_released_capacity": False,
            "expected_version": None,
        },
    )
    assert configured.status_code == 200
    assert configured.json()["maximum_concurrent_workstreams"] == 2


@pytest.mark.asyncio
async def test_machine_inventory_does_not_enroll_or_trust_worker(
    capacity_api_database: ServiceFixture,
) -> None:
    app = app_for(capacity_api_database, tuple(EngineeringCapacityPermission.ALL))
    recorded = await request(
        app,
        "POST",
        "/api/v1/engineering/capacity/machines",
        json={"machine_label": "Laptop 1", "expected_available_on": "2026-08-04"},
    )
    assert recorded.status_code == 200
    assert recorded.json()["enrollment_state"] == "unenrolled"
    assert recorded.json()["worker_id"] is None
