from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from app.core.config import settings
from app.platform.company.models import Company
from app.platform.factory_control.router import overview
from app.platform.factory_control.schemas import FactoryEventIn
from app.platform.factory_control.service import factory_control_service
from app.platform.users.models import User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_overview_api_is_tenant_scoped(database) -> None:
    first = Company(name="Factory One", code="FACTORYONE", timezone="UTC")
    second = Company(name="Factory Two", code="FACTORYTWO", timezone="UTC")
    actor = User(
        normalized_email="factory-owner@example.test",
        first_name="Factory",
        last_name="Owner",
        display_name="Factory Owner",
        status="active",
    )
    async with database() as session, session.begin():
        session.add_all([first, second, actor])

    milestone = factory_control_service.roadmap().milestones[0].code
    occurred_at = datetime(2026, 9, 18, tzinfo=timezone.utc)
    async with database() as session, session.begin():
        await factory_control_service.ingest(
            session,
            company_id=first.id,
            actor_user_id=actor.id,
            data=FactoryEventIn(
                lane_code="OM1-1",
                milestone_code=milestone,
                event_type="work_started",
                lifecycle_state="active",
                queue_depth=1,
                idempotency_key="tenant-one-event",
                occurred_at=occurred_at,
            ),
        )
        await factory_control_service.ingest(
            session,
            company_id=second.id,
            actor_user_id=actor.id,
            data=FactoryEventIn(
                lane_code="OM2-1",
                milestone_code=milestone,
                event_type="queued",
                lifecycle_state="queued",
                queue_depth=2,
                idempotency_key="tenant-two-event",
                occurred_at=occurred_at,
            ),
        )

    async with database() as session:
        response = await overview(
            context=SimpleNamespace(company=SimpleNamespace(id=first.id)),  # type: ignore[arg-type]
            session=session,
        )

    assert [lane.lane_code for lane in response.lanes] == ["OM1-1"]
    assert response.metrics.queue_depth == 1
    assert response.roadmap_milestones > 0


@pytest.mark.asyncio
async def test_snapshot_key_replay_returns_original_without_duplicate(database) -> None:
    company = Company(name="Snapshot Factory", code="SNAPSHOTFACTORY", timezone="UTC")
    actor = User(
        normalized_email="snapshot-owner@example.test",
        first_name="Snapshot",
        last_name="Owner",
        display_name="Snapshot Owner",
        status="active",
    )
    async with database() as session, session.begin():
        session.add_all([company, actor])
    async with database() as session, session.begin():
        first, duplicate = await factory_control_service.capture_snapshot(
            session,
            company_id=company.id,
            actor_user_id=actor.id,
            snapshot_key="controller-cycle-1",
            now=datetime(2026, 9, 18, tzinfo=timezone.utc),
        )
        replay, replay_duplicate = await factory_control_service.capture_snapshot(
            session,
            company_id=company.id,
            actor_user_id=actor.id,
            snapshot_key="controller-cycle-1",
            now=datetime(2026, 9, 19, tzinfo=timezone.utc),
        )
    assert duplicate is False
    assert replay_duplicate is True
    assert replay.id == first.id
    assert replay.captured_at == first.captured_at
