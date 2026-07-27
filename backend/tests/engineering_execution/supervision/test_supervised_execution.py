from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_execution.composition.models import (
    NormalizedProviderResult,
    ProviderExecutionAttempt,
)
from app.engineering_execution.status.service import MobileExecutionStatusService
from app.engineering_execution.supervision.contracts import CreateProviderSession
from app.engineering_execution.supervision.errors import SupervisionIneligibleError
from app.engineering_execution.supervision.execution import (
    ExecuteApprovedComposition,
    SupervisedExecutionService,
)
from app.engineering_execution.supervision.service import (
    LiveClientSupervisor,
    ProviderSessionService,
)
from app.execution_providers.contracts import (
    ProviderCapabilities,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.execution_providers.errors import ProviderUnavailableError
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
from tests.engineering_execution.status.test_execution_status import read_context
from tests.engineering_execution.test_engineering_execution import execution_context


class FakeExecutionRuntime:
    def __init__(self, capabilities: ProviderCapabilities) -> None:
        self._capabilities = capabilities
        self.requests: list[
            tuple[ProviderRuntimeRequest, ProviderExecutionRequest]
        ] = []
        self.close_calls = 0

    def capabilities(self, provider_identifier: str) -> ProviderCapabilities:
        assert provider_identifier == "codex"
        return self._capabilities

    async def open(self, request):
        raise AssertionError("readiness request must not run before execution")

    async def supervise(self, request):
        raise AssertionError("not used")

    async def cancel(self, request):
        raise AssertionError("not used")

    async def recover(self, request):
        raise AssertionError("not used")

    async def execute(self, request, execution):
        self.requests.append((request, execution))
        now = datetime.now(timezone.utc)
        return ProviderExecutionResult(
            provider_request_id=execution.provider_request_id,
            execution_id=execution.execution_id,
            provider_execution_id="bounded-result",
            provider_identifier="codex",
            status=ProviderExecutionStatus.SUCCEEDED,
            started_at=now,
            finished_at=now,
            evidence_summary={
                "structured_text": "Truthful monitoring preserves approval integrity.",
            },
            validation_summary={"bounded_output": True, "output_tokens": 7},
            output_references=(),
            failure_classification=None,
            provider_session_reference=execution.provider_session_reference,
        )

    async def close(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        self.close_calls += 1
        return ProviderRuntimeResult(
            provider_session_id=request.provider_session_id,
            state=ProviderRuntimeState.CLOSED,
            observed_at=utc_now(),
            failure_classification=None,
            credential_status=ProviderCredentialStatus.USABLE,
            provider_session_reference=request.provider_session_reference,
        )


class FailingExecutionRuntime(FakeExecutionRuntime):
    async def execute(self, request, execution):
        self.requests.append((request, execution))
        raise ProviderUnavailableError("safe provider failure")


@pytest_asyncio.fixture
async def execution_database() -> AsyncIterator[ServiceFixture]:
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


async def prepared_execution(fixture: ServiceFixture):
    service, compose, command, _, worker, _, provider = await composition_scenario(
        fixture,
        instruction=(
            "Return a short structured explanation of why truthful fail-closed "
            "provider monitoring matters in an approval-gated engineering system."
        ),
        requested_code_changes=False,
    )
    async with fixture.factory() as session:
        bundle = await service.compose(
            session,
            context=execution_context(fixture.context),
            command=compose,
        )
    async with fixture.factory() as session:
        attempt = await service.prepare_attempt(
            session,
            context=execution_context(fixture.context),
            composition_id=bundle.composition.id,
            idempotency_key=uuid4(),
        )
    context = worker_context(worker)
    runtime = FakeExecutionRuntime(provider.capabilities)
    async with fixture.factory() as session:
        await LiveClientSupervisor().start(session, context=context)
    sessions = ProviderSessionService(runtime=runtime)
    async with fixture.factory() as session:
        provider_session = await sessions.create(
            session,
            context=context,
            command=CreateProviderSession(
                bundle.composition.id,
                attempt.id,
                60,
            ),
        )
    return (
        command,
        bundle,
        attempt,
        context,
        runtime,
        sessions,
        provider_session,
    )


@pytest.mark.asyncio
async def test_supervised_execution_is_durable_idempotent_and_disconnects(
    execution_database: ServiceFixture,
) -> None:
    fixture = execution_database
    (
        command,
        _,
        attempt,
        context,
        runtime,
        sessions,
        provider_session,
    ) = await prepared_execution(fixture)
    service = SupervisedExecutionService(runtime=runtime)
    async with fixture.factory() as session:
        before = await MobileExecutionStatusService().get(
            session,
            context=read_context(fixture),
            command_id=command.id,
        )
    async with fixture.factory() as session:
        outcome = await service.execute(
            session,
            context=context,
            command=ExecuteApprovedComposition(
                provider_session.id,
                attempt.idempotency_key,
                128,
                30,
            ),
        )
    async with fixture.factory() as session:
        during = await MobileExecutionStatusService().get(
            session,
            context=read_context(fixture),
            command_id=command.id,
        )
        stored = await session.scalar(
            select(NormalizedProviderResult).where(
                NormalizedProviderResult.attempt_id == attempt.id
            )
        )
    assert before.execution_connected is False
    assert during.execution_connected is True
    assert outcome.durable_result.repository_mutated is False
    assert stored is not None
    assert str(stored.evidence_summary["structured_text"]).startswith("Truthful")
    assert len(runtime.requests) == 1
    assert runtime.requests[0][1].repository_key == ""
    assert runtime.requests[0][1].authorized_code_changes is False
    async with fixture.factory() as session:
        closed = await sessions.shutdown(
            session,
            context=context,
            record=outcome.provider_session,
        )
    async with fixture.factory() as session:
        after = await MobileExecutionStatusService().get(
            session,
            context=read_context(fixture),
            command_id=command.id,
        )
    assert closed.runtime_state is ProviderRuntimeState.CLOSED
    assert after.execution_connected is False
    assert runtime.close_calls == 1
    async with fixture.factory() as session:
        with pytest.raises(SupervisionIneligibleError):
            await service.execute(
                session,
                context=context,
                command=ExecuteApprovedComposition(
                    provider_session.id,
                    attempt.idempotency_key,
                ),
            )
    assert len(runtime.requests) == 1


@pytest.mark.asyncio
async def test_wrong_offer_fails_before_provider_invocation(
    execution_database: ServiceFixture,
) -> None:
    fixture = execution_database
    _, _, _, context, runtime, _, provider_session = await prepared_execution(fixture)
    async with fixture.factory() as session:
        with pytest.raises(SupervisionIneligibleError):
            await SupervisedExecutionService(runtime=runtime).execute(
                session,
                context=context,
                command=ExecuteApprovedComposition(
                    provider_session.id,
                    uuid4(),
                ),
            )
    assert runtime.requests == []
    async with fixture.factory() as session:
        attempt = await session.get(
            ProviderExecutionAttempt,
            provider_session.attempt_id,
        )
    assert attempt is not None
    assert attempt.state == "prepared"


@pytest.mark.asyncio
async def test_provider_failure_is_durable_safe_and_not_retried(
    execution_database: ServiceFixture,
) -> None:
    fixture = execution_database
    _, _, attempt, context, runtime, _, provider_session = await prepared_execution(
        fixture
    )
    failing = FailingExecutionRuntime(runtime._capabilities)
    async with fixture.factory() as session:
        with pytest.raises(ProviderUnavailableError):
            await SupervisedExecutionService(runtime=failing).execute(
                session,
                context=context,
                command=ExecuteApprovedComposition(
                    provider_session.id,
                    attempt.idempotency_key,
                ),
            )
    async with fixture.factory() as session:
        stored = await session.scalar(
            select(NormalizedProviderResult).where(
                NormalizedProviderResult.attempt_id == attempt.id
            )
        )
        current = await session.get(ProviderExecutionAttempt, attempt.id)
    assert len(failing.requests) == 1
    assert stored is not None
    assert stored.status == "failed"
    assert stored.repository_mutated is False
    assert current is not None
    assert current.state == "failed"
