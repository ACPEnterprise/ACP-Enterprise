from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.mobile.control import WorkstreamControlRepository
from app.engineering_control.mobile.notifications import (
    MissionNotificationService,
    notification_kind,
)
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
from tests.engineering_control.test_engineering_command_service import (
    seed_service_fixture,
)


def test_notifications_exist_only_when_owner_action_can_change_state() -> None:
    assert (
        notification_kind(
            SimpleNamespace(runtime_state="waiting_for_owner", reason_code=None)  # type: ignore[arg-type]
        )
        == "waiting_for_owner"
    )
    assert (
        notification_kind(
            SimpleNamespace(
                runtime_state="recovering", reason_code="reconciliation_required"
            )  # type: ignore[arg-type]
        )
        == "manual_recovery"
    )
    for state, reason in (
        ("running", None),
        ("completed", "deployment_completed"),
        ("failed", "deployment_failed"),
        ("recovering", "heartbeat_expired"),
    ):
        assert (
            notification_kind(
                SimpleNamespace(runtime_state=state, reason_code=reason)  # type: ignore[arg-type]
            )
            is None
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
        assert runtime.worker_health == "healthy"
        assert runtime.reason_code is None
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
        running.worker_health = "unhealthy"
        running.reason_code = "heartbeat_expired"

    heartbeat_at = now + timedelta(minutes=4)
    async with worker_database.factory() as session, session.begin():
        refreshed = await service.refresh_attached_heartbeats(
            session,
            context=worker_context,
            session_id=session_id,
            health="healthy",
            now=heartbeat_at,
        )
        assert refreshed == 1

    async with worker_database.factory() as session:
        refreshed_runtime = await session.scalar(
            select(EngineeringWorkstreamRuntime).where(
                EngineeringWorkstreamRuntime.command_id == command.id
            )
        )
        assert refreshed_runtime is not None
        assert refreshed_runtime.version == initial_version + 1
        assert refreshed_runtime.heartbeat_at == heartbeat_at
        assert refreshed_runtime.worker_health == "healthy"
        assert refreshed_runtime.reason_code is None
        assert refreshed_runtime.acknowledgement_expires_at == (
            heartbeat_at + timedelta(minutes=5)
        )

    async with worker_database.factory() as session, session.begin():
        wrong_session = await service.refresh_attached_heartbeats(
            session,
            context=worker_context,
            session_id=uuid4(),
            health="healthy",
            now=heartbeat_at + timedelta(seconds=1),
        )
        assert wrong_session == 0

    async with worker_database.factory() as session:
        reconnect_pending = await service.pending(
            session,
            context=worker_context,
            session_id=uuid4(),
            now=heartbeat_at + timedelta(seconds=1),
        )
        assert tuple(item.id for item in reconnect_pending) == (control.id,)

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
            session, context=worker_context, now=heartbeat_at + timedelta(minutes=6)
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
        assert total == 0
        assert not any(item.command_id == command.id for item in rows)
    recovery_payloads = await _events_after(
        worker_context.company_id, UUID(str(command_payloads[-1]["event_id"]))
    )
    recovery_payload = next(
        item for item in recovery_payloads if item["command_id"] == str(command.id)
    )
    assert recovery_payload["runtime_state"] == "recovering"
    assert recovery_payload["notifications"] == ()


@pytest.mark.asyncio
async def test_durable_provider_progress_advances_phone_runtime_monotonically(
    worker_database_fixture,
) -> None:
    fixture = worker_database_fixture
    command = await approved_command(fixture)
    _, _, worker_context, _ = await register_available_worker(fixture)
    service = WorkstreamRuntimeService()
    now = worker_context.authenticated_at + timedelta(seconds=2)
    async with fixture.factory() as session, session.begin():
        control = await WorkstreamControlRepository.set_state(
            session,
            company_id=worker_context.company_id,
            command_id=command.id,
            actor_user_id=fixture.context.user.id,
            desired_state="active",
            requested_action="start",
            reason="owner_start",
            occurred_at=now,
        )
        await service.acknowledge(
            session,
            context=worker_context,
            session_id=uuid4(),
            control_id=control.id,
            expected_control_version=control.version,
            action="start",
            idempotency_key="progress-ack",
            reason_code=None,
            now=now,
        )
    attempt_id = uuid4()
    async with fixture.factory() as session, session.begin():
        executing = await service.project_provider_progress(
            session,
            company_id=worker_context.company_id,
            command_id=command.id,
            attempt_id=attempt_id,
            sequence_number=1,
            phase="executing",
            percentage=None,
            summary="Applying bounded changes",
            message_code="bounded_changes",
            occurred_at=now + timedelta(seconds=1),
        )
        assert executing is not None
        assert executing.runtime_state == "running"
        assert executing.progress_percent == 25
    async with fixture.factory() as session, session.begin():
        validating = await service.project_provider_progress(
            session,
            company_id=worker_context.company_id,
            command_id=command.id,
            attempt_id=attempt_id,
            sequence_number=2,
            phase="validating",
            percentage=72,
            summary="Running validation",
            message_code="validation_running",
            occurred_at=now + timedelta(seconds=2),
        )
        assert validating is not None
        assert validating.runtime_state == "validating"
        assert validating.progress_percent == 80
        version = validating.version
    async with fixture.factory() as session, session.begin():
        duplicate = await service.project_provider_progress(
            session,
            company_id=worker_context.company_id,
            command_id=command.id,
            attempt_id=attempt_id,
            sequence_number=2,
            phase="validating",
            percentage=72,
            summary="Running validation",
            message_code="validation_running",
            occurred_at=now + timedelta(seconds=3),
        )
        assert duplicate is not None
        assert duplicate.version == version
    async with fixture.factory() as session:
        event_count = await session.scalar(
            select(func.count(EngineeringWorkstreamEvent.id)).where(
                EngineeringWorkstreamEvent.command_id == command.id,
                EngineeringWorkstreamEvent.event_type == "provider_progress",
            )
        )
    assert event_count == 2


@pytest.mark.asyncio
async def test_reconnect_clears_stale_health_only_when_execution_never_began(
    worker_database_fixture,
) -> None:
    worker_database = worker_database_fixture
    command = await approved_command(worker_database)
    _, _, worker_context, _ = await register_available_worker(worker_database)
    now = worker_context.authenticated_at + timedelta(seconds=2)
    service = WorkstreamRuntimeService()
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
        runtime = await service.acknowledge(
            session,
            context=worker_context,
            session_id=uuid4(),
            control_id=control.id,
            expected_control_version=control.version,
            action="start",
            idempotency_key="initial-session",
            reason_code=None,
            now=now,
        )
        runtime.runtime_state = "recovering"
        runtime.worker_health = "unhealthy"
        runtime.reason_code = "heartbeat_expired"

    async with worker_database.factory() as session, session.begin():
        recovered = await service.acknowledge(
            session,
            context=worker_context,
            session_id=uuid4(),
            control_id=control.id,
            expected_control_version=control.version,
            action="start",
            idempotency_key="replacement-session",
            reason_code=None,
            now=now + timedelta(minutes=6),
        )
        assert recovered.runtime_state == "acknowledged"
        assert recovered.worker_health == "healthy"
        assert recovered.reason_code is None

        recovered.runtime_state = "recovering"
        recovered.worker_health = "unhealthy"
        recovered.reason_code = "heartbeat_expired"
        recovered.current_activity = "Executing controlled workstream"

    async with worker_database.factory() as session, session.begin():
        ambiguous = await service.acknowledge(
            session,
            context=worker_context,
            session_id=uuid4(),
            control_id=control.id,
            expected_control_version=control.version,
            action="start",
            idempotency_key="ambiguous-replacement-session",
            reason_code=None,
            now=now + timedelta(minutes=12),
        )
        assert ambiguous.runtime_state == "waiting_for_owner"
        assert ambiguous.worker_health == "healthy"
        assert ambiguous.reason_code == "reconciliation_required"
