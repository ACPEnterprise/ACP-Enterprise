from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_control.commands import CreateEngineeringCommand
from app.engineering_control.service import EngineeringControlService
from app.engineering_execution.service import EngineeringExecutionService
from app.engineering_execution.status.contracts import (
    CommandStatusSource,
    ConnectionState,
    ExecutionStatusSource,
    ExecutionStatusSources,
    HeartbeatStatusSource,
    LeasePhase,
    LeaseStatusSource,
    MonitoringState,
    SupervisorStatusSource,
    TransportSessionStatusSource,
)
from app.engineering_execution.status.service import (
    ExecutionStatusNotFoundError,
    MobileExecutionStatusService,
)
from app.platform.permissions.authorization import (
    AuthorizationError,
    PermissionDeniedError,
)
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)
from tests.engineering_execution.test_engineering_execution import (
    approved_command,
    execution_context,
)


@pytest_asyncio.fixture
async def status_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


def read_context(fixture: ServiceFixture):
    return context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        (EngineeringCommandPermission.READ,),
    )


@pytest.mark.asyncio
async def test_projection_is_honest_before_approval_and_without_execution(
    status_database: ServiceFixture,
) -> None:
    fixture = status_database
    control = EngineeringControlService()
    command_context = context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        tuple(EngineeringCommandPermission.ALL),
    )
    async with fixture.factory() as session:
        command = await control.create_command(
            session,
            context=command_context,
            command=CreateEngineeringCommand(
                command_type="owner_instruction",
                owner_instruction="Inspect only the approved monitoring boundary.",
                repository_key="acp-enterprise",
                expected_branch="customer-management-v1",
                expected_head="a" * 40,
                requested_code_changes=False,
                expires_at=utc_now() + timedelta(hours=2),
                idempotency_key=uuid4().hex,
                execution_boundary={
                    "allowed_repository": "acp-enterprise",
                    "allowed_branch": "customer-management-v1",
                    "expected_head": "a" * 40,
                    "allowed_paths": ["**"],
                    "forbidden_paths": [".git/**", ".env*", "**/.env*"],
                    "permitted_operations": ["inspect", "validate"],
                    "validation_requirements": ["git diff --check"],
                },
            ),
        )

    service = MobileExecutionStatusService()
    async with fixture.factory() as session:
        pending = await service.get(
            session, context=read_context(fixture), command_id=command.id
        )
    assert pending.monitoring_state is MonitoringState.NOT_APPROVED
    assert pending.execution_available is False
    assert pending.execution_connected is False
    assert pending.execution_id is None
    assert pending.lease.status is None
    assert pending.heartbeat.last_seen is None
    assert pending.result.status is None
    assert pending.progress_label == "Awaiting owner approval"
    assert pending.polling_after_seconds == 60

    approved = await approved_command(fixture)
    async with fixture.factory() as session:
        waiting = await service.get(
            session, context=read_context(fixture), command_id=approved.id
        )
    assert waiting.monitoring_state is MonitoringState.APPROVED_NOT_DISPATCHABLE
    assert waiting.progress_label == "Approved; dispatch unavailable"
    assert waiting.execution_available is False


@pytest.mark.asyncio
async def test_disconnected_execution_projection_is_minimized_and_company_scoped(
    status_database: ServiceFixture,
) -> None:
    fixture = status_database
    command = await approved_command(fixture)
    execution_service = EngineeringExecutionService()
    async with fixture.factory() as session:
        execution = await execution_service.request_execution(
            session,
            context=execution_context(fixture.context),
            command_id=command.id,
        )

    service = MobileExecutionStatusService()
    async with fixture.factory() as session:
        projected = await service.get(
            session, context=read_context(fixture), command_id=command.id
        )
    assert projected.monitoring_state is MonitoringState.DISCONNECTED
    assert projected.execution_id == execution.execution_id
    assert projected.execution_state == "execution_not_connected"
    assert projected.execution_status == "disconnected"
    assert projected.execution_connected is False
    assert projected.progress_label == "Execution not connected"
    assert projected.lease.availability == "unavailable"
    assert projected.heartbeat.availability == "unavailable"
    assert projected.result.failure_classification == "provider_not_connected"
    assert [entry.event for entry in projected.timeline] == [
        "execution_requested",
        "command_updated",
    ]

    other = context_with_permissions(
        fixture.other_context.user,
        fixture.other_context.company,
        fixture.other_context.membership,
        (EngineeringCommandPermission.READ,),
    )
    async with fixture.factory() as session:
        with pytest.raises(ExecutionStatusNotFoundError):
            await service.get(session, context=other, command_id=command.id)


@pytest.mark.asyncio
async def test_read_permission_and_active_membership_are_required(
    status_database: ServiceFixture,
) -> None:
    fixture = status_database
    command = await approved_command(fixture)
    service = MobileExecutionStatusService()
    missing_permission = context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        (EngineeringExecutionPermission.REQUEST,),
    )
    inactive = replace(
        read_context(fixture),
        membership=replace(read_context(fixture).membership, status="suspended"),
    )

    async with fixture.factory() as session:
        with pytest.raises(PermissionDeniedError):
            await service.get(
                session, context=missing_permission, command_id=command.id
            )
        with pytest.raises(AuthorizationError):
            await service.get(session, context=inactive, command_id=command.id)


def test_live_connectivity_projection_uses_only_persisted_transport_evidence() -> None:
    now = utc_now()
    worker_id = uuid4()
    sources = ExecutionStatusSources(
        command=CommandStatusSource(
            command_id=uuid4(),
            ecid="ECID-2026-000001",
            approval_state="approved",
            command_updated_at=now - timedelta(minutes=4),
        ),
        execution=ExecutionStatusSource(
            execution_id=uuid4(),
            state="execution_not_connected",
            status="disconnected",
            requested_at=now - timedelta(minutes=3),
            started_at=None,
            finished_at=None,
            updated_at=now - timedelta(minutes=3),
            failure_classification="provider_not_connected",
            validation_available=False,
            evidence_available=False,
            output_reference_count=0,
        ),
        lease=LeaseStatusSource(
            lease_id=uuid4(),
            worker_id=worker_id,
            status="active",
            started_at=now - timedelta(minutes=2),
            expires_at=now + timedelta(seconds=45),
            released_at=None,
        ),
        heartbeat=HeartbeatStatusSource(
            health="healthy", last_seen=now - timedelta(seconds=12)
        ),
        transport_session=TransportSessionStatusSource(
            state="active",
            established_at=now - timedelta(minutes=2),
            expires_at=now + timedelta(minutes=5),
            last_message_at=now - timedelta(seconds=8),
        ),
        result=None,
        supervisor=SupervisorStatusSource(
            supervisor_state="recovering",
            session_state="opening",
            runtime_state="initializing",
            credential_status="unavailable",
            provider_ready=False,
            ready=False,
            updated_at=now - timedelta(seconds=6),
            expires_at=now + timedelta(minutes=4),
            failure_classification=None,
        ),
    )

    projected = MobileExecutionStatusService._project(sources, now=now)

    assert projected.connection_state is ConnectionState.CONNECTED
    assert projected.execution_connected is False
    assert projected.transport_health == "healthy"
    assert projected.heartbeat.age_seconds == 12
    assert projected.lease.phase is LeasePhase.EXPIRING
    assert projected.lease.worker_id == worker_id
    assert projected.transport_session.last_contact_at == now - timedelta(seconds=8)
    assert projected.supervisor.state == "recovering"
    assert projected.supervisor.session_state == "opening"
    assert projected.supervisor.recovering is True
    assert projected.supervisor.ready is False
    assert projected.polling_after_seconds == 10
    timeline_events = {entry.event for entry in projected.timeline}
    assert "transport_contact" in timeline_events
    assert "supervisor_state_updated" in timeline_events

    assert sources.supervisor is not None
    provider_ready = MobileExecutionStatusService._project(
        replace(
            sources,
            supervisor=replace(
                sources.supervisor,
                session_state="ready",
                runtime_state="provider_ready",
                credential_status="usable",
                provider_ready=True,
                ready=True,
            ),
        ),
        now=now,
    )
    assert provider_ready.execution_connected is True
    assert provider_ready.supervisor.provider_ready is True


def test_stale_transport_evidence_is_disconnected_not_progress() -> None:
    now = utc_now()
    sources = ExecutionStatusSources(
        command=CommandStatusSource(
            command_id=uuid4(),
            ecid="ECID-2026-000002",
            approval_state="approved",
            command_updated_at=now,
        ),
        execution=None,
        lease=None,
        heartbeat=HeartbeatStatusSource(
            health="healthy", last_seen=now - timedelta(minutes=5)
        ),
        transport_session=None,
        result=None,
    )

    projected = MobileExecutionStatusService._project(sources, now=now)

    assert projected.connection_state is ConnectionState.DISCONNECTED
    assert projected.transport_health == "stale"
    assert projected.monitoring_state is MonitoringState.APPROVED_NOT_DISPATCHABLE
    assert projected.polling_after_seconds == 60
