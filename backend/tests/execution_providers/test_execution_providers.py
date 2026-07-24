from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import inspect
from uuid import uuid4

import pytest

from app.execution_providers.codex import (
    CodexClientAuthenticationError,
    CodexClientUnavailableError,
    CodexExecutionProvider,
    CodexOperation,
    CodexOperationResult,
)
from app.execution_providers.contracts import (
    ProviderCapability,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderHealth,
)
from app.execution_providers.errors import (
    DuplicateProviderError,
    ProviderAuthenticationError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from app.execution_providers.registry import ExecutionProviderRegistry
from app.worker_control import service as worker_control_service_module


def now() -> datetime:
    return datetime.now(timezone.utc)


class FakeCodexClient:
    def __init__(self) -> None:
        self.operation: CodexOperation | None = None
        self.failure: Exception | None = None

    async def health(self) -> ProviderHealth:
        return ProviderHealth(True, now(), "ready")

    async def execute(self, operation: CodexOperation) -> CodexOperationResult:
        self.operation = operation
        if self.failure is not None:
            raise self.failure
        return CodexOperationResult(
            operation_id="codex-operation-1",
            succeeded=True,
            started_at=now(),
            finished_at=now(),
            evidence_summary={"repository_mutated": False},
            validation_summary={"tests_run": False},
            output_references=("evidence://codex-operation-1",),
        )


def request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider_request_id=uuid4(),
        execution_id=uuid4(),
        lease_id=uuid4(),
        company_id=uuid4(),
        worker_id=uuid4(),
        provider_identifier="codex",
        repository_key="acp-enterprise",
        expected_branch="customer-management-v1",
        expected_head="a" * 40,
        authorized_code_changes=True,
        instruction="Implement only the approved bounded change.",
        instruction_digest="b" * 64,
        request_digest="c" * 64,
        correlation_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_registry_registration_resolution_capabilities_and_health() -> None:
    provider = CodexExecutionProvider(
        client=FakeCodexClient(),
        model="codex-test-model",
        implementation_version="1",
    )
    registry = ExecutionProviderRegistry()
    registry.register(provider)
    assert registry.resolve("codex") is provider
    assert registry.capabilities("codex").supports(
        ProviderCapability.ENGINEERING_EXECUTE
    )
    assert (await registry.health("codex")).available is True
    with pytest.raises(DuplicateProviderError):
        registry.register(provider)
    with pytest.raises(ProviderNotFoundError):
        registry.resolve("unknown")


@pytest.mark.asyncio
async def test_codex_adapter_translates_request_and_result() -> None:
    client = FakeCodexClient()
    provider = CodexExecutionProvider(
        client=client,
        model="codex-test-model",
        implementation_version="1",
    )
    provider_request = request()
    result = await provider.execute(provider_request)
    assert client.operation == CodexOperation(
        idempotency_key=provider_request.provider_request_id,
        model="codex-test-model",
        instruction=provider_request.instruction,
        repository_key=provider_request.repository_key,
        expected_branch=provider_request.expected_branch,
        expected_head=provider_request.expected_head,
        allow_code_changes=True,
        correlation_id=provider_request.correlation_id,
    )
    assert result.status is ProviderExecutionStatus.SUCCEEDED
    assert result.provider_identifier == "codex"
    assert result.provider_execution_id == "codex-operation-1"
    with pytest.raises(TypeError):
        result.evidence_summary["unsafe"] = True  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.provider_identifier = "other"  # type: ignore[misc]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_error", "expected_error"),
    [
        (CodexClientAuthenticationError(), ProviderAuthenticationError),
        (CodexClientUnavailableError(), ProviderUnavailableError),
    ],
)
async def test_codex_adapter_translates_structured_failures(
    client_error: Exception, expected_error: type[Exception]
) -> None:
    client = FakeCodexClient()
    client.failure = client_error
    provider = CodexExecutionProvider(
        client=client,
        model="codex-test-model",
        implementation_version="1",
    )
    with pytest.raises(expected_error):
        await provider.execute(request())


@pytest.mark.asyncio
async def test_codex_adapter_rejects_wrong_provider_identity() -> None:
    provider = CodexExecutionProvider(
        client=FakeCodexClient(),
        model="codex-test-model",
        implementation_version="1",
    )
    wrong = replace(request(), provider_identifier="other")
    with pytest.raises(ProviderAuthenticationError):
        await provider.execute(wrong)


def test_worker_control_has_no_codex_dependency() -> None:
    assert "execution_providers.codex" not in inspect.getsource(
        worker_control_service_module
    )
