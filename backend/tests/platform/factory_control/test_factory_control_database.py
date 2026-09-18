import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from app.core.config import settings
from app.database.session import get_database_session, get_security_database_session
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import access_token_service
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.factory_control.authority import (
    grant_factory_controller_authority,
    grant_platform_factory_reader,
    revoke_platform_authority_assignment,
)
from app.platform.factory_control.models import (
    FactoryControlEvent,
    FactoryLaneState,
    PlatformAuthorityAssignment,
)
from app.platform.factory_control.router import router as factory_control_router
from app.platform.factory_control.schemas import FactoryEventIn, FactoryLiveLaneTarget
from app.platform.factory_control.service import (
    FactoryEventConflict,
    factory_control_service,
)
from app.platform.users.models import User, UserCredential
from app.worker_control.contracts import AuthenticatedWorkerContext
from app.worker_control.models import EngineeringWorker
from app.worker_control.transport.http.dependencies import (
    WorkerHttpIdentity,
    get_worker_http_identity,
)
from app.worker_identity.models import WorkerIdentity
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@dataclass(frozen=True)
class ControllerFixture:
    company_id: UUID
    worker_id: UUID
    identity_id: UUID
    actor_id: UUID


@pytest_asyncio.fixture
async def database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_controller(
    database: async_sessionmaker[AsyncSession], *, label: str
) -> ControllerFixture:
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    company = Company(
        id=uuid4(), name=f"{label} Company", code=label.upper(), timezone="UTC"
    )
    actor = User(
        id=uuid4(),
        normalized_email=f"{label.lower()}-{uuid4()}@example.test",
        first_name="Factory",
        last_name="Controller",
        display_name="Factory Controller",
        status="active",
    )
    membership = Membership(
        id=uuid4(),
        user_id=actor.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=True,
    )
    worker = EngineeringWorker(
        id=uuid4(),
        company_id=company.id,
        provider_identifier="factory-test",
        name=f"{label}-lane",
        worker_version="1",
        capabilities=["engineering.execute"],
        lifecycle_state="available",
        registered_by_user_id=actor.id,
        registered_at=now,
        last_heartbeat_at=now,
        updated_at=now,
    )
    identity = WorkerIdentity(
        id=uuid4(),
        company_id=company.id,
        name=f"{label} identity",
        state="active",
        registered_by_user_id=actor.id,
        orchestration_worker_id=worker.id,
        version=1,
        registered_at=now,
        updated_at=now,
    )
    async with database() as session, session.begin():
        session.add_all([company, actor])
        await session.flush()
        session.add(membership)
        await session.flush()
        session.add(worker)
        await session.flush()
        session.add(identity)
    return ControllerFixture(company.id, worker.id, identity.id, actor.id)


def event(
    fixture: ControllerFixture,
    *,
    key: str,
    state: str = "ACTIVE",
    queue_depth: int = 1,
    occurred_at: datetime | None = None,
) -> FactoryEventIn:
    return FactoryEventIn(
        tenant_company_id=fixture.company_id,
        lane_code="OM1-A",
        event_type="work_started",
        lifecycle_state=state,
        queue_depth=queue_depth,
        idempotency_key=key,
        occurred_at=occurred_at or datetime(2026, 9, 18, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_overview_is_platform_global_with_optional_tenant_evidence(
    database,
) -> None:
    first = await seed_controller(database, label=f"GLOBALA{uuid4().hex[:6]}")
    second = await seed_controller(database, label=f"GLOBALB{uuid4().hex[:6]}")
    async with database() as session, session.begin():
        await factory_control_service.ingest(
            session,
            controller_worker_identity_id=first.identity_id,
            controller_tenant_company_id=first.company_id,
            data=event(first, key=f"global-a-{uuid4()}", queue_depth=1),
        )
        await factory_control_service.ingest(
            session,
            controller_worker_identity_id=second.identity_id,
            controller_tenant_company_id=second.company_id,
            data=event(
                second,
                key=f"global-b-{uuid4()}",
                state="ELIGIBLE_IDLE",
                queue_depth=2,
            ).model_copy(update={"lane_code": "OM2-B"}),
        )
    async with database() as session:
        _, events, lanes, metrics, _ = await factory_control_service.overview(session)
    assert {first.company_id, second.company_id} <= {
        row.tenant_company_id for row in events
    }
    assert {"OM1-A", "OM2-B"} <= {row.lane_code for row in lanes}
    assert metrics["queue_depth"] >= 3


@pytest.mark.asyncio
async def test_event_exact_replay_and_changed_queue_depth_conflict(database) -> None:
    fixture = await seed_controller(database, label=f"REPLAY{uuid4().hex[:6]}")
    evidence = event(fixture, key=f"replay-{uuid4()}")
    async with database() as session, session.begin():
        first, duplicate = await factory_control_service.ingest(
            session,
            controller_worker_identity_id=fixture.identity_id,
            controller_tenant_company_id=fixture.company_id,
            data=evidence,
        )
        replay, replayed = await factory_control_service.ingest(
            session,
            controller_worker_identity_id=fixture.identity_id,
            controller_tenant_company_id=fixture.company_id,
            data=evidence,
        )
    assert duplicate is False
    assert replayed is True
    assert replay.id == first.id
    assert first.queue_depth == 1
    async with database() as session, session.begin():
        with pytest.raises(FactoryEventConflict):
            await factory_control_service.ingest(
                session,
                controller_worker_identity_id=fixture.identity_id,
                controller_tenant_company_id=fixture.company_id,
                data=evidence.model_copy(update={"queue_depth": 2}),
            )


@pytest.mark.asyncio
async def test_concurrent_distinct_events_for_absent_lane_are_deterministic(
    database,
) -> None:
    fixture = await seed_controller(database, label=f"LANE{uuid4().hex[:6]}")
    occurred = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    prefix = f"lane-{uuid4()}"
    lower = event(
        fixture,
        key=f"{prefix}-a",
        state="ACTIVE",
        queue_depth=1,
        occurred_at=occurred,
    ).model_copy(update={"lane_code": prefix})
    higher = event(
        fixture,
        key=f"{prefix}-b",
        state="ELIGIBLE_IDLE",
        queue_depth=3,
        occurred_at=occurred,
    ).model_copy(update={"lane_code": prefix})

    async def ingest(data: FactoryEventIn) -> None:
        async with database() as session, session.begin():
            await factory_control_service.ingest(
                session,
                controller_worker_identity_id=fixture.identity_id,
                controller_tenant_company_id=fixture.company_id,
                data=data,
            )

    await asyncio.gather(ingest(higher), ingest(lower))
    async with database() as session:
        lane = await session.scalar(
            select(FactoryLaneState).where(FactoryLaneState.lane_code == prefix)
        )
    assert lane is not None
    assert lane.last_event_key == higher.idempotency_key
    assert lane.lifecycle_state == "ELIGIBLE_IDLE"
    assert lane.queue_depth == 3


@pytest.mark.asyncio
async def test_snapshot_replay_rejects_changed_capture_facts(database) -> None:
    fixture = await seed_controller(database, label=f"SNAP{uuid4().hex[:6]}")
    key = f"snapshot-{uuid4()}"
    captured = datetime(2026, 9, 18, tzinfo=timezone.utc)
    async with database() as session, session.begin():
        first, duplicate = await factory_control_service.capture_snapshot(
            session,
            controller_worker_identity_id=fixture.identity_id,
            controller_tenant_company_id=fixture.company_id,
            snapshot_key=key,
            captured_at=captured,
        )
        replay, replayed = await factory_control_service.capture_snapshot(
            session,
            controller_worker_identity_id=fixture.identity_id,
            controller_tenant_company_id=fixture.company_id,
            snapshot_key=key,
            captured_at=captured,
        )
    assert duplicate is False
    assert replayed is True
    assert replay.id == first.id
    async with database() as session, session.begin():
        with pytest.raises(FactoryEventConflict):
            await factory_control_service.capture_snapshot(
                session,
                controller_worker_identity_id=fixture.identity_id,
                controller_tenant_company_id=fixture.company_id,
                snapshot_key=key,
                captured_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
            )


@pytest.mark.asyncio
async def test_http_read_requires_active_authenticated_global_grant(database) -> None:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        normalized_email=f"platform-{uuid4()}@example.test",
        first_name="Platform",
        last_name="Owner",
        display_name="Platform Owner",
        status="active",
        authorization_version=1,
    )
    ungranted = User(
        id=uuid4(),
        normalized_email=f"tenant-{uuid4()}@example.test",
        first_name="Tenant",
        last_name="Owner",
        display_name="Tenant Owner",
        status="active",
        authorization_version=1,
    )
    disabled = User(
        id=uuid4(),
        normalized_email=f"disabled-{uuid4()}@example.test",
        first_name="Disabled",
        last_name="Owner",
        display_name="Disabled Owner",
        status="disabled",
        authorization_version=1,
    )
    users = (user, ungranted, disabled)
    sessions = []
    tokens = []
    for current in users:
        credential = UserCredential(
            id=uuid4(),
            user_id=current.id,
            password_hash="$argon2id$test-only-encoded-hash",
            password_changed_at=now,
            credential_version=1,
        )
        authentication_session = AuthenticationSession(
            id=uuid4(),
            user_id=current.id,
            status="active",
            created_at=now,
            last_seen_at=now,
            absolute_expires_at=now + timedelta(days=1),
            idle_expires_at=now + timedelta(hours=12),
            authentication_method="password",
            credential_version=1,
            authorization_version=1,
        )
        sessions.append((credential, authentication_session))
        tokens.append(
            access_token_service.issue(
                user_id=current.id,
                session_id=authentication_session.id,
                credential_version=1,
                authorization_version=1,
                now=now,
            )[0]
        )
    grant = PlatformAuthorityAssignment(
        principal_type="USER",
        user_id=user.id,
        authority_code="PLATFORM_OWNER",
        permission_code="PLATFORM_FACTORY_CONTROL_READ",
        status="active",
        grant_reason="Explicit test platform custody grant",
        granted_by_user_id=user.id,
        granted_at=now,
        version=1,
    )
    async with database() as session, session.begin():
        session.add_all(users)
        await session.flush()
        session.add_all([item for pair in sessions for item in pair])
        session.add(grant)

    app = FastAPI()
    app.include_router(factory_control_router)

    async def session_override():
        async with database() as session:
            yield session

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_security_database_session] = session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        permitted = await client.get(
            "/api/v1/platform/factory-control/overview",
            headers={"Authorization": f"Bearer {tokens[0]}"},
        )
        tenant_only = await client.get(
            "/api/v1/platform/factory-control/overview",
            headers={"Authorization": f"Bearer {tokens[1]}"},
        )
        inactive = await client.get(
            "/api/v1/platform/factory-control/overview",
            headers={"Authorization": f"Bearer {tokens[2]}"},
        )
        human_post = await client.post(
            "/api/v1/platform/factory-control/internal/events",
            headers={"Authorization": f"Bearer {tokens[0]}"},
            json={},
        )
    assert permitted.status_code == 200
    overview = permitted.json()
    assert overview["roadmap_milestones"] == 60
    assert overview["metrics"]["represented_milestones"] == 60
    assert overview["metrics"]["engineering_count"] == 29
    assert overview["metrics"]["beta_count"] == 1
    assert overview["metrics"]["owner_count"] == 1
    assert overview["metrics"]["closed_count"] == 1
    assert overview["telemetry_freshness"] in {"LIVE", "NOT_YET_MEASURED"}
    assert tenant_only.status_code == 403
    assert inactive.status_code == 401
    assert human_post.status_code == 401

    async with database() as session, session.begin():
        await revoke_platform_authority_assignment(
            session,
            assignment_id=grant.id,
            revoked_by_user_id=user.id,
            reason="Test revocation",
            revoked_at=now,
        )
        persisted_user = await session.get(User, user.id)
        assert persisted_user is not None
        assert persisted_user.authorization_version == 2
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        revoked = await client.get(
            "/api/v1/platform/factory-control/overview",
            headers={"Authorization": f"Bearer {tokens[0]}"},
        )
    assert revoked.status_code == 401


@pytest.mark.asyncio
async def test_http_ingest_requires_exact_active_global_worker_grant(database) -> None:
    fixture = await seed_controller(database, label=f"HTTPWORKER{uuid4().hex[:6]}")
    app = FastAPI()
    app.include_router(factory_control_router)

    async def session_override():
        async with database() as session:
            yield session

    async def worker_identity_override():
        return WorkerHttpIdentity(
            context=AuthenticatedWorkerContext(
                company_id=fixture.company_id,
                worker_id=fixture.worker_id,
                provider_identifier="factory-test",
                authentication_subject="credential:test-public-key",
                authenticated_at=datetime.now(timezone.utc),
            ),
            session_id=uuid4(),
        )

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_security_database_session] = session_override
    app.dependency_overrides[get_worker_http_identity] = worker_identity_override
    transport = httpx.ASGITransport(app=app)
    payload = event(fixture, key=f"http-worker-{uuid4()}").model_dump(mode="json")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ungranted = await client.post(
            "/api/v1/platform/factory-control/internal/events", json=payload
        )
    assert ungranted.status_code == 403

    grant = PlatformAuthorityAssignment(
        principal_type="WORKER_IDENTITY",
        worker_identity_id=fixture.identity_id,
        authority_code="FACTORY_CONTROLLER",
        permission_code="PLATFORM_FACTORY_CONTROL_INGEST",
        status="active",
        grant_reason="Explicit test controller authority",
        granted_by_user_id=fixture.actor_id,
        granted_at=datetime.now(timezone.utc),
        version=1,
    )
    async with database() as session, session.begin():
        session.add(grant)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post(
            "/api/v1/platform/factory-control/internal/events", json=payload
        )
    assert accepted.status_code == 202

    async with database() as session, session.begin():
        persisted = await session.get(PlatformAuthorityAssignment, grant.id)
        assert persisted is not None
        persisted.status = "revoked"
        persisted.revoked_at = datetime.now(timezone.utc)
        persisted.revoked_by_user_id = fixture.actor_id
        persisted.revocation_reason = "Test controller revocation"
        persisted.version += 1
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        revoked = await client.post(
            "/api/v1/platform/factory-control/internal/events", json=payload
        )
    assert revoked.status_code == 403


@pytest.mark.asyncio
async def test_existing_controller_sync_connection_projects_authoritative_worker_state(
    database,
) -> None:
    fixture = await seed_controller(database, label=f"HTTPSYNC{uuid4().hex[:6]}")
    grant = PlatformAuthorityAssignment(
        principal_type="WORKER_IDENTITY",
        worker_identity_id=fixture.identity_id,
        authority_code="FACTORY_CONTROLLER",
        permission_code="PLATFORM_FACTORY_CONTROL_INGEST",
        status="active",
        grant_reason="Explicit isolated controller-sync acceptance grant",
        granted_by_user_id=fixture.actor_id,
        granted_at=datetime.now(timezone.utc),
        version=1,
    )
    async with database() as session, session.begin():
        session.add(grant)

    app = FastAPI()
    app.include_router(factory_control_router)

    async def session_override():
        async with database() as session:
            yield session

    async def worker_identity_override():
        return WorkerHttpIdentity(
            context=AuthenticatedWorkerContext(
                company_id=fixture.company_id,
                worker_id=fixture.worker_id,
                provider_identifier="factory-test",
                authentication_subject="credential:test-public-key",
                authenticated_at=datetime.now(timezone.utc),
            ),
            session_id=uuid4(),
        )

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_security_database_session] = session_override
    app.dependency_overrides[get_worker_http_identity] = worker_identity_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post("/api/v1/platform/factory-control/internal/sync")
        replay = await client.post("/api/v1/platform/factory-control/internal/sync")
    assert accepted.status_code == 202
    assert accepted.json()["duplicate"] is False
    assert replay.status_code == 202
    assert replay.json()["duplicate"] is True
    async with database() as session:
        lane = await session.scalar(
            select(FactoryLaneState).where(
                FactoryLaneState.lane_code.like("HTTPSYNC%")
            )
        )
        persisted = await session.scalar(
            select(FactoryControlEvent).where(
                FactoryControlEvent.controller_worker_identity_id
                == fixture.identity_id,
                FactoryControlEvent.event_type == "controller_sync",
            )
        )
    assert lane is not None
    assert lane.lifecycle_state == "ELIGIBLE_IDLE"
    assert persisted is not None
    assert persisted.source == "development_factory_controller"


@pytest.mark.asyncio
async def test_governed_activation_grants_exact_human_and_narrow_controller(
    database,
) -> None:
    fixture = await seed_controller(database, label=f"ACTIVATE{uuid4().hex[:6]}")
    async with database() as session, session.begin():
        grant, created = await grant_platform_factory_reader(
            session,
            user_id=fixture.actor_id,
            exact_display_name="Factory Controller",
            granted_by_user_id=fixture.actor_id,
            reason="Explicit owner-authorized Factory Control activation",
        )
        controller = await grant_factory_controller_authority(
            session,
            worker_identity_id=fixture.identity_id,
            granted_by_user_id=fixture.actor_id,
            reason="Narrow live Factory telemetry controller",
        )
    assert created is True
    assert grant.authority_code == "PLATFORM_ADMIN"
    assert {item.permission_code for item, _ in controller} == {
        "PLATFORM_FACTORY_CONTROL_INGEST",
        "PLATFORM_FACTORY_CONTROL_SNAPSHOT",
    }
    async with database() as session, session.begin():
        replay, replay_created = await grant_platform_factory_reader(
            session,
            user_id=fixture.actor_id,
            exact_display_name="Factory Controller",
            granted_by_user_id=fixture.actor_id,
            reason="Exact replay",
        )
    assert replay.id == grant.id
    assert replay_created is False


@pytest.mark.asyncio
async def test_governed_activation_fails_closed_on_nonexact_human(database) -> None:
    fixture = await seed_controller(database, label=f"EXACT{uuid4().hex[:6]}")
    async with database() as session:
        with pytest.raises(ValueError, match="Exact active Factory Control user"):
            async with session.begin():
                await grant_platform_factory_reader(
                    session,
                    user_id=fixture.actor_id,
                    exact_display_name="Different Human",
                    granted_by_user_id=fixture.actor_id,
                    reason="Must not match fuzzily",
                )


@pytest.mark.asyncio
async def test_live_sync_projects_canonical_controller_lane_heartbeat(database) -> None:
    fixture = await seed_controller(database, label=f"LIVE{uuid4().hex[:6]}")
    observed_at = datetime.now(timezone.utc)
    target = FactoryLiveLaneTarget(
        lane_code="OM1E",
        worker_id=fixture.worker_id,
        controlling_enterprise="OM1E",
        lifecycle_state="ACTIVE",
        self_refill_health="SELF_REFILL_HEALTHY",
        milestone_code="DEVELOPMENT.FACTORY",
        current_assignment="Qualify current release",
        queue_depth=1,
        evidence=["protected release assignment"],
    )
    async with database() as session, session.begin():
        first = await factory_control_service.sync_authoritative_lanes(
            session,
            controller_worker_identity_id=fixture.identity_id,
            controller_tenant_company_id=fixture.company_id,
            targets=[target],
            observed_at=observed_at,
        )
    async with database() as session, session.begin():
        replay = await factory_control_service.sync_authoritative_lanes(
            session,
            controller_worker_identity_id=fixture.identity_id,
            controller_tenant_company_id=fixture.company_id,
            targets=[target],
            observed_at=observed_at,
        )
    assert first[0][1] is False
    assert replay[0][1] is True
    async with database() as session:
        lane = await session.scalar(
            select(FactoryLaneState).where(FactoryLaneState.lane_code == "OM1E")
        )
    assert lane is not None
    assert lane.controlling_enterprise == "OM1E"
    assert lane.lifecycle_state == "ACTIVE"
    assert lane.current_assignment == "Qualify current release"
    assert lane.queue_depth == 1
    assert lane.last_event_at == observed_at
