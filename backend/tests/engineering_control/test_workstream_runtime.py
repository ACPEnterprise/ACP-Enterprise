from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_control.mobile.control import WorkstreamControlRepository
from app.engineering_control.workstream_runtime import (
    EngineeringWorkstreamEvent,
    WorkstreamRuntimeError,
    WorkstreamRuntimeService,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.engineering_control.test_engineering_command_service import (
    seed_service_fixture,
)
from tests.engineering_execution.test_engineering_execution import approved_command
from tests.worker_control.test_worker_control import (
    register_available_worker,
)


@pytest_asyncio.fixture
async def worker_database_fixture():
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield fixture
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_acknowledgement_is_idempotent_versioned_and_recoverable(
    worker_database_fixture,
) -> None:
    worker_database = worker_database_fixture
    command = await approved_command(worker_database)
    _, _, worker_context, _ = await register_available_worker(worker_database)
    now = worker_context.authenticated_at + timedelta(seconds=2)
    async with worker_database.factory() as session, session.begin():
        control = await WorkstreamControlRepository.set_state(
            session,
            company_id=worker_context.company_id,
            command_id=command.id,
            actor_user_id=worker_database.context.user.id,
            desired_state="active",
            requested_action="start",
            reason="owner_start",
            occurred_at=now,
        )

    service = WorkstreamRuntimeService()
    async with worker_database.factory() as session:
        pending = await service.pending(session, context=worker_context, now=now)
        assert tuple(item.id for item in pending) == (control.id,)

    session_id = uuid4()
    async with worker_database.factory() as session, session.begin():
        runtime = await service.acknowledge(
            session,
            context=worker_context,
            session_id=session_id,
            control_id=control.id,
            expected_control_version=control.version,
            action="start",
            idempotency_key="ack-start-1",
            reason_code=None,
            now=now,
        )
        assert runtime.runtime_state == "acknowledged"
        initial_version = runtime.version

    async with worker_database.factory() as session, session.begin():
        duplicate = await service.acknowledge(
            session,
            context=worker_context,
            session_id=session_id,
            control_id=control.id,
            expected_control_version=control.version,
            action="start",
            idempotency_key="ack-start-1",
            reason_code=None,
            now=now + timedelta(seconds=1),
        )
        assert duplicate.version == initial_version

    async with worker_database.factory() as session, session.begin():
        running = await service.transition(
            session,
            context=worker_context,
            session_id=session_id,
            command_id=command.id,
            expected_version=initial_version,
            runtime_state="running",
            health="healthy",
            progress_percent=25,
            current_activity="Running validation",
            reason_code=None,
            idempotency_key="runtime-running-1",
            now=now + timedelta(seconds=2),
        )
        assert running.version == initial_version + 1
        assert running.progress_percent == 25

    async with worker_database.factory() as session, session.begin():
        with pytest.raises(WorkstreamRuntimeError, match="stale"):
            await service.transition(
                session,
                context=worker_context,
                session_id=session_id,
                command_id=command.id,
                expected_version=initial_version,
                runtime_state="completed",
                health="healthy",
                progress_percent=100,
                current_activity=None,
                reason_code=None,
                idempotency_key="runtime-stale",
                now=now + timedelta(seconds=3),
            )

    async with worker_database.factory() as session:
        recovery = await service.pending(
            session, context=worker_context, now=now + timedelta(minutes=6)
        )
        event_count = await session.scalar(
            select(func.count(EngineeringWorkstreamEvent.id)).where(
                EngineeringWorkstreamEvent.command_id == command.id
            )
        )
        assert tuple(item.id for item in recovery) == (control.id,)
        assert event_count == 2
