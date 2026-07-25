import asyncio
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_execution.composition.models import ProviderExecutionAttempt
from app.engineering_execution.supervision.contracts import (
    CreateProviderSession,
    ProviderSessionState,
    SupervisorState,
)
from app.engineering_execution.supervision.errors import (
    SupervisionCapabilityError,
    SupervisionNotFoundError,
    SupervisionTransitionError,
)
from app.engineering_execution.supervision.service import (
    LiveClientSupervisor,
    ProviderSessionService,
)
from app.execution_providers.contracts import ProviderCapabilities
from app.execution_providers.errors import ProviderRequestError
from app.execution_providers.registry import ExecutionProviderRegistry
from app.execution_providers.runtime import (
    ProviderCredentialStatus,
    ProviderRuntimeRequest,
    ProviderRuntimeResult,
    ProviderRuntimeState,
)
from app.worker_control.contracts import AuthenticatedWorkerContext
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    seed_service_fixture,
    utc_now,
)
from tests.engineering_execution.composition.test_composition import (
    composition_scenario,
)
from tests.engineering_execution.test_engineering_execution import execution_context
from tests.worker_control.test_worker_control import FakeExecutionProvider


class InterfaceOnlyRuntime:
    """Test composition seam whose operational methods must remain unused."""

    def __init__(self, registry: ExecutionProviderRegistry) -> None:
        self.registry = registry
        self.operation_calls: list[str] = []

    def capabilities(self, provider_identifier: str) -> ProviderCapabilities:
        return self.registry.capabilities(provider_identifier)

    async def open(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("open")
        raise AssertionError("Provider runtime operations are unavailable.")

    async def supervise(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("supervise")
        raise AssertionError("Provider runtime operations are unavailable.")

    async def cancel(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("cancel")
        raise AssertionError("Provider runtime operations are unavailable.")

    async def close(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("close")
        raise AssertionError("Provider runtime operations are unavailable.")

    async def recover(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("recover")
        raise AssertionError("Provider runtime operations are unavailable.")


class ReadyRuntime(InterfaceOnlyRuntime):
    async def open(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("open")
        return ProviderRuntimeResult(
            provider_session_id=request.provider_session_id,
            state=ProviderRuntimeState.PROVIDER_READY,
            observed_at=utc_now(),
            failure_classification=None,
            credential_status=ProviderCredentialStatus.USABLE,
            provider_session_reference="provider-session-reference",
        )

    async def close(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("close")
        return ProviderRuntimeResult(
            provider_session_id=request.provider_session_id,
            state=ProviderRuntimeState.CLOSED,
            observed_at=utc_now(),
            failure_classification=None,
            credential_status=ProviderCredentialStatus.USABLE,
            provider_session_reference=request.provider_session_reference,
        )


class ModelAccessFailureRuntime(InterfaceOnlyRuntime):
    async def open(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.operation_calls.append("open")
        raise ProviderRequestError("model inaccessible")


def runtime_for(*providers: FakeExecutionProvider) -> InterfaceOnlyRuntime:
    return InterfaceOnlyRuntime(ExecutionProviderRegistry(providers))


@pytest_asyncio.fixture
async def supervision_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


def worker_context(worker) -> AuthenticatedWorkerContext:
    return AuthenticatedWorkerContext(
        company_id=worker.company_id,
        worker_id=worker.id,
        provider_identifier=worker.provider_identifier,
        authentication_subject=f"worker:{worker.id}",
        authenticated_at=utc_now(),
    )


async def scenario(fixture: ServiceFixture):
    (
        composition_service,
        compose,
        _,
        _,
        worker,
        _,
        provider,
    ) = await composition_scenario(fixture)
    async with fixture.factory() as session:
        bundle = await composition_service.compose(
            session,
            context=execution_context(fixture.context),
            command=compose,
        )
    async with fixture.factory() as session:
        attempt = await composition_service.prepare_attempt(
            session,
            context=execution_context(fixture.context),
            composition_id=bundle.composition.id,
            idempotency_key=uuid4(),
        )
    return bundle, attempt, worker, provider


def test_supervision_contracts_are_immutable_and_provider_neutral() -> None:
    command = CreateProviderSession(uuid4(), uuid4(), 300)
    with pytest.raises(FrozenInstanceError):
        command.timeout_seconds = 10  # type: ignore[misc]
    root = Path(__file__).parents[3] / "app" / "engineering_execution" / "supervision"
    source = "\n".join(path.read_text() for path in root.glob("*.py"))
    runtime_source = (
        Path(__file__).parents[3] / "app" / "execution_providers" / "runtime.py"
    ).read_text()
    assert "execution_providers.codex" not in source
    assert "provider.execute(" not in source
    assert ".health(" not in source
    assert "httpx" not in source
    assert "subprocess" not in source
    assert "ExecutionProvider" not in source
    assert "class ProviderRuntime(Protocol)" in runtime_source
    assert "execution_providers.codex" not in runtime_source
    assert "httpx" not in runtime_source
    assert "socket" not in runtime_source
    assert "subprocess" not in runtime_source


@pytest.mark.asyncio
async def test_supervisor_start_is_idempotent_and_concurrency_safe(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    _, _, worker, _ = await scenario(fixture)
    context = worker_context(worker)
    supervisor = LiveClientSupervisor()

    async def start():
        async with fixture.factory() as session:
            return await supervisor.start(session, context=context)

    first, second = await asyncio.gather(start(), start())
    assert first.id == second.id
    assert first.state is second.state is SupervisorState.READY


@pytest.mark.asyncio
async def test_provider_session_lifecycle_never_invokes_provider(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    bundle, attempt, worker, provider = await scenario(fixture)
    context = worker_context(worker)
    async with fixture.factory() as session:
        await LiveClientSupervisor().start(session, context=context)
    runtime = runtime_for(provider)
    sessions = ProviderSessionService(runtime=runtime)
    async with fixture.factory() as session:
        record = await sessions.create(
            session,
            context=context,
            command=CreateProviderSession(
                composition_id=bundle.composition.id,
                attempt_id=attempt.id,
                timeout_seconds=300,
            ),
        )
    assert record.state is ProviderSessionState.CREATED
    assert record.approved_code_changes is bundle.composition.approved_code_changes
    for state in (
        ProviderSessionState.OPENING,
        ProviderSessionState.READY,
        ProviderSessionState.ACTIVE,
        ProviderSessionState.CLOSING,
        ProviderSessionState.CLOSED,
    ):
        async with fixture.factory() as session:
            record = await sessions.transition(
                session,
                context=context,
                session_id=record.id,
                expected_version=record.version,
                to_state=state,
            )
    assert record.state is ProviderSessionState.CLOSED
    assert provider.requests == []
    assert runtime.operation_calls == []


@pytest.mark.asyncio
async def test_provider_runtime_establishment_stops_before_execution(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    bundle, attempt, worker, provider = await scenario(fixture)
    context = worker_context(worker)
    async with fixture.factory() as session:
        await LiveClientSupervisor().start(session, context=context)
    runtime = ReadyRuntime(ExecutionProviderRegistry((provider,)))
    sessions = ProviderSessionService(runtime=runtime)
    async with fixture.factory() as session:
        created = await sessions.create(
            session,
            context=context,
            command=CreateProviderSession(bundle.composition.id, attempt.id, 300),
        )
    async with fixture.factory() as session:
        ready = await sessions.open(session, context=context, record=created)

    assert ready.state is ProviderSessionState.READY
    assert ready.runtime_state is ProviderRuntimeState.PROVIDER_READY
    assert ready.credential_status is ProviderCredentialStatus.USABLE
    assert ready.provider_ready is True
    assert ready.provider_session_reference == "provider-session-reference"
    assert runtime.operation_calls == ["open"]
    assert provider.requests == []
    async with fixture.factory() as session:
        closed = await sessions.shutdown(session, context=context, record=ready)
    assert closed.state is ProviderSessionState.CLOSED
    assert closed.runtime_state is ProviderRuntimeState.CLOSED
    assert closed.provider_ready is False
    assert runtime.operation_calls == ["open", "close"]


@pytest.mark.asyncio
async def test_model_access_failure_is_classified_without_readiness(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    bundle, attempt, worker, provider = await scenario(fixture)
    context = worker_context(worker)
    async with fixture.factory() as session:
        await LiveClientSupervisor().start(session, context=context)
    service = ProviderSessionService(
        runtime=ModelAccessFailureRuntime(ExecutionProviderRegistry((provider,)))
    )
    async with fixture.factory() as session:
        record = await service.create(
            session,
            context=context,
            command=CreateProviderSession(
                composition_id=bundle.composition.id,
                attempt_id=attempt.id,
                timeout_seconds=300,
            ),
        )
    async with fixture.factory() as session:
        failed = await service.open(session, context=context, record=record)
    assert failed.failure_classification == "model_access_failure"
    assert failed.provider_ready is False


@pytest.mark.asyncio
async def test_timeout_cancellation_and_invalid_transition(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    bundle, attempt, worker, provider = await scenario(fixture)
    context = worker_context(worker)
    async with fixture.factory() as session:
        await LiveClientSupervisor().start(session, context=context)
    sessions = ProviderSessionService(runtime=runtime_for(provider))
    async with fixture.factory() as session:
        record = await sessions.create(
            session,
            context=context,
            command=CreateProviderSession(bundle.composition.id, attempt.id, 30),
        )
    async with fixture.factory() as session:
        expired = await sessions.transition(
            session,
            context=context,
            session_id=record.id,
            expected_version=record.version,
            to_state=ProviderSessionState.EXPIRED,
            now=record.expires_at,
        )
    assert expired.state is ProviderSessionState.EXPIRED
    async with fixture.factory() as session:
        with pytest.raises(SupervisionTransitionError):
            await sessions.transition(
                session,
                context=context,
                session_id=record.id,
                expected_version=expired.version,
                to_state=ProviderSessionState.ACTIVE,
            )


@pytest.mark.asyncio
async def test_cancellation_supervision_is_acknowledgement_only(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    bundle, attempt, worker, provider = await scenario(fixture)
    context = worker_context(worker)
    async with fixture.factory() as session:
        await LiveClientSupervisor().start(session, context=context)
    runtime = runtime_for(provider)
    sessions = ProviderSessionService(runtime=runtime)
    async with fixture.factory() as session:
        record = await sessions.create(
            session,
            context=context,
            command=CreateProviderSession(bundle.composition.id, attempt.id, 300),
        )
    async with fixture.factory() as session:
        cancelled = await sessions.transition(
            session,
            context=context,
            session_id=record.id,
            expected_version=record.version,
            to_state=ProviderSessionState.CANCELLED,
        )

    assert cancelled.state is ProviderSessionState.CANCELLED
    assert cancelled.closed_at is not None
    assert provider.requests == []
    assert runtime.operation_calls == []


@pytest.mark.asyncio
async def test_recovery_uses_durable_attempt_and_cancellation_state(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    bundle, attempt, worker, _ = await scenario(fixture)
    async with fixture.factory() as session, session.begin():
        stored = await session.get(ProviderExecutionAttempt, attempt.id)
        assert stored is not None
        stored.cancellation_requested_at = utc_now()
    context = worker_context(worker)
    async with fixture.factory() as session:
        recovery = await LiveClientSupervisor().recover(session, context=context)
    assert recovery.items
    item = next(
        item for item in recovery.items if item.composition_id == bundle.composition.id
    )
    assert item.attempt_id == attempt.id
    assert item.cancellation_requested is True


@pytest.mark.asyncio
async def test_capability_and_company_mismatch_fail_closed(
    supervision_database: ServiceFixture,
) -> None:
    fixture = supervision_database
    bundle, attempt, worker, _ = await scenario(fixture)
    context = worker_context(worker)
    async with fixture.factory() as session:
        await LiveClientSupervisor().start(session, context=context)
    incapable = FakeExecutionProvider(
        identifier=worker.provider_identifier, capabilities=()
    )
    service = ProviderSessionService(runtime=runtime_for(incapable))
    async with fixture.factory() as session:
        with pytest.raises(SupervisionCapabilityError):
            await service.create(
                session,
                context=context,
                command=CreateProviderSession(bundle.composition.id, attempt.id, 300),
            )
    wrong_company = AuthenticatedWorkerContext(
        company_id=uuid4(),
        worker_id=context.worker_id,
        provider_identifier=context.provider_identifier,
        authentication_subject=context.authentication_subject,
        authenticated_at=context.authenticated_at,
    )
    capable = ProviderSessionService(
        runtime=runtime_for(
            FakeExecutionProvider(identifier=worker.provider_identifier)
        )
    )
    async with fixture.factory() as session:
        with pytest.raises(SupervisionNotFoundError):
            await capable.create(
                session,
                context=wrong_company,
                command=CreateProviderSession(bundle.composition.id, attempt.id, 300),
            )
