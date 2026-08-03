from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from app.core.config import settings
from app.database.session import get_database_session
from app.engineering_capacity.router import router
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCapacityPermission
from app.platform.permissions.dependencies import get_authorization_context
from app.worker_control.models import EngineeringWorker
from app.worker_identity.models import WorkerCredential, WorkerIdentity
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
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


@pytest.mark.asyncio
async def test_owner_configures_existing_authenticated_worker_by_name(
    capacity_api_database: ServiceFixture,
) -> None:
    fixture = capacity_api_database
    now = utc_now()
    worker = EngineeringWorker(
        id=uuid4(),
        company_id=fixture.context.company.id,
        provider_identifier="authenticated-transport",
        name="ACP Office Engineering Node",
        worker_version="1",
        capabilities=["engineering.execute"],
        lifecycle_state="available",
        registered_by_user_id=fixture.context.user.id,
        registered_at=now,
        last_heartbeat_at=now,
    )
    identity = WorkerIdentity(
        id=uuid4(),
        company_id=fixture.context.company.id,
        name="Office node identity",
        state="active",
        registered_by_user_id=fixture.context.user.id,
        orchestration_worker_id=worker.id,
        version=1,
        registered_at=now,
        updated_at=now,
    )
    credential = WorkerCredential(
        company_id=fixture.context.company.id,
        identity_id=identity.id,
        version=1,
        state="active",
        verifier="test-verifier",
        verifier_algorithm="ed25519",
        public_key_id=f"api-test-{uuid4()}",
        issued_at=now,
        expires_at=now + timedelta(days=1),
        activated_at=now,
        updated_at=now,
    )
    async with fixture.factory() as session, session.begin():
        session.add(worker)
        await session.flush()
        session.add(identity)
        await session.flush()
        session.add(credential)

    manage_app = app_for(fixture, tuple(EngineeringCapacityPermission.ALL))
    policy = await request(
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
    assert policy.status_code == 200
    eligible = await request(
        manage_app, "GET", "/api/v1/engineering/capacity/eligible-workers"
    )
    assert eligible.status_code == 200
    assert eligible.json()[0]["worker_name"] == "ACP Office Engineering Node"

    configured = await request(
        manage_app,
        "POST",
        "/api/v1/engineering/capacity/workers/configure-existing",
        json={
            "worker_id": str(worker.id),
            "machine_label": "Original Office Machine",
            "configured_limit": 1,
            "idempotency_key": f"phone-setup-{worker.id}",
        },
    )
    assert configured.status_code == 200
    assert configured.json()["worker_id"] == str(worker.id)
    summary = await request(manage_app, "GET", "/api/v1/engineering/capacity/summary")
    assert summary.json()["configured_capacity"] == 1
    assert summary.json()["available_capacity"] == 1
    assert summary.json()["active_allocations"] == []
    assert summary.json()["active_reservations"] == []

    read_app = app_for(fixture, (EngineeringCapacityPermission.READ,))
    denied = await request(
        read_app,
        "POST",
        "/api/v1/engineering/capacity/workers/configure-existing",
        json={
            "worker_id": str(worker.id),
            "machine_label": "Different machine",
            "configured_limit": 1,
            "idempotency_key": "denied",
        },
    )
    assert denied.status_code == 403
