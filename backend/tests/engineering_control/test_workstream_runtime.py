from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_control.mobile.control import WorkstreamControlRepository
from app.engineering_control.mobile.notifications import MissionNotificationService
from app.engineering_control.mobile.realtime import (
    InvalidResumeToken,
    _events_after,
    persist_expired_heartbeats,
    validate_resume_token,
)
from app.engineering_control.workstream_runtime import (
    EngineeringWorkstreamEvent,
    EngineeringWorkstreamRuntime,
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
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
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

    payloads = await _events_after(worker_context.company_id, None)
    command_payloads = tuple(
        item for item in payloads if item["command_id"] == str(command.id)
    )
    assert [item["event_type"] for item in command_payloads] == [
        "worker_acknowledgement",
        "runtime_transition",
    ]
    assert command_payloads[-1]["acknowledgement_latency_ms"] is None
    assert command_payloads[-1]["reconnect_count"] == 0
    replay = await _events_after(
        worker_context.company_id, UUID(str(command_payloads[0]["event_id"]))
    )
    assert [
        item["event_id"] for item in replay if item["command_id"] == str(command.id)
    ] == [command_payloads[1]["event_id"]]

    async with worker_database.factory() as session:
        with pytest.raises(InvalidResumeToken):
            await validate_resume_token(session, worker_context.company_id, uuid4())

    stale_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    async with worker_database.factory() as session, session.begin():
        persisted = await session.scalar(
            select(EngineeringWorkstreamRuntime).where(
                EngineeringWorkstreamRuntime.command_id == command.id
            )
        )
        assert persisted is not None
        persisted.heartbeat_at = stale_at
        persisted.updated_at = stale_at
    await persist_expired_heartbeats(worker_context.company_id)
    async with worker_database.factory() as session:
        recovered = await session.scalar(
            select(EngineeringWorkstreamRuntime).where(
                EngineeringWorkstreamRuntime.command_id == command.id
            )
        )
        expired = await session.scalar(
            select(EngineeringWorkstreamEvent).where(
                EngineeringWorkstreamEvent.command_id == command.id,
                EngineeringWorkstreamEvent.reason_code == "heartbeat_expired",
            )
        )
        assert recovered is not None and recovered.runtime_state == "recovering"
        assert recovered.worker_health == "unhealthy"
        assert expired is not None

    notifications = MissionNotificationService()
    async with worker_database.factory() as session:
        rows, total = await notifications.list(
            session,
            context=worker_database.context,
            page=1,
            page_size=25,
            now=datetime.now(timezone.utc),
        )
        heartbeat_notice = next(item for item in rows if item.command_id == command.id)
        assert total >= 1
        assert heartbeat_notice.kind == "heartbeat_expired"
        assert heartbeat_notice.severity == "warning"

    async with worker_database.factory() as session:
        escalated, _ = await notifications.list(
            session,
            context=worker_database.context,
            page=1,
            page_size=25,
            now=datetime.now(timezone.utc) + timedelta(minutes=6),
        )
        heartbeat_notice = next(
            item for item in escalated if item.command_id == command.id
        )
        assert heartbeat_notice.severity == "critical"
        assert heartbeat_notice.escalated_at is not None

    async with worker_database.factory() as session:
        acknowledged = await notifications.acknowledge(
            session,
            context=worker_database.context,
            notification_id=heartbeat_notice.id,
            expected_version=heartbeat_notice.version,
        )
        assert acknowledged.status == "acknowledged"
        assert acknowledged.acknowledged_by_user_id == worker_database.context.user.id
    recovery_payloads = await _events_after(
        worker_context.company_id, UUID(str(command_payloads[-1]["event_id"]))
    )
    recovery_payload = next(
        item for item in recovery_payloads if item["command_id"] == str(command.id)
    )
    assert recovery_payload["runtime_state"] == "recovering"
    assert recovery_payload["notifications"] == (
        "recovering",
        "worker_offline",
        "heartbeat_expired",
    )
