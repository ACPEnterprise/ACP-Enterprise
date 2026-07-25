import inspect
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.execution_providers.codex import (
    CodexClientAuthenticationError,
    CodexClientUnavailableError,
    CodexExecutionProvider,
    CodexOperation,
    CodexOperationResult,
    CodexSessionRequest,
    CodexSessionResult,
)
from app.execution_providers.contracts import (
    ProviderCapabilities,
    ProviderCapability,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderHealth,
    ProviderSessionRequest,
    ProviderSessionStatus,
)
from app.execution_providers.errors import (
    DuplicateProviderError,
    ProviderAuthenticationError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from app.execution_providers.registry import ExecutionProviderRegistry
from app.execution_providers.runtime import (
    ProviderCredentialResolution,
    ProviderCredentialStatus,
    ProviderRuntimeRequest,
    ProviderRuntimeState,
    RegistryProviderRuntime,
)
from app.worker_control import service as worker_control_service_module


def now() -> datetime:
    return datetime.now(timezone.utc)


class FakeCodexClient:
    def __init__(self) -> None:
        self.operation: CodexOperation | None = None
        self.failure: Exception | None = None
        self.session_request: CodexSessionRequest | None = None

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

    async def open_session(self, request: CodexSessionRequest) -> CodexSessionResult:
        self.session_request = request
        if self.failure is not None:
            raise self.failure
        return CodexSessionResult("codex-session-1", True, now())

    async def close_session(self, session_reference: str) -> CodexSessionResult:
        return CodexSessionResult(session_reference, True, now())

    async def cancel_session(self, session_reference: str) -> CodexSessionResult:
        return CodexSessionResult(session_reference, True, now())

    async def recover_session(self, session_reference: str) -> CodexSessionResult:
        return CodexSessionResult(session_reference, True, now())


class FakeCredentialResolver:
    def __init__(self, status: ProviderCredentialStatus) -> None:
        self.status = status

    async def resolve(
        self,
        *,
        company_id: UUID,
        worker_id: UUID,
        provider_identifier: str,
        now: datetime,
    ) -> ProviderCredentialResolution:
        return ProviderCredentialResolution(
            status=self.status,
            credential_reference=(
                "opaque-credential-reference"
                if self.status is ProviderCredentialStatus.USABLE
                else None
            ),
            expires_at=now + timedelta(hours=1),
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


def session_request() -> ProviderSessionRequest:
    return ProviderSessionRequest(
        provider_session_id=uuid4(),
        company_id=uuid4(),
        worker_id=uuid4(),
        provider_identifier="codex",
        capabilities=ProviderCapabilities((ProviderCapability.ENGINEERING_EXECUTE,)),
        credential_reference="credential-reference",
        provider_session_reference=None,
        expires_at=now(),
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
async def test_codex_adapter_establishes_session_without_execution() -> None:
    client = FakeCodexClient()
    provider = CodexExecutionProvider(
        client=client,
        model="codex-test-model",
        implementation_version="1",
    )
    provider_request = session_request()

    result = await provider.open_session(provider_request)

    assert result.status is ProviderSessionStatus.READY
    assert result.provider_session_reference == "codex-session-1"
    assert client.session_request == CodexSessionRequest(
        session_id=provider_request.provider_session_id,
        credential_reference="credential-reference",
        expires_at=provider_request.expires_at,
    )
    assert client.operation is None


@pytest.mark.asyncio
async def test_runtime_opens_codex_session_without_execution_or_secret_output() -> None:
    client = FakeCodexClient()
    provider = CodexExecutionProvider(
        client=client,
        model="codex-test-model",
        implementation_version="1",
    )
    runtime = RegistryProviderRuntime(
        providers=ExecutionProviderRegistry((provider,)),
        credentials=FakeCredentialResolver(ProviderCredentialStatus.USABLE),
    )
    runtime_request = ProviderRuntimeRequest(
        provider_session_id=uuid4(),
        company_id=uuid4(),
        worker_id=uuid4(),
        provider_identifier="codex",
        capabilities=provider.capabilities,
        expires_at=now() + timedelta(minutes=10),
    )

    result = await runtime.open(runtime_request)

    assert result.state is ProviderRuntimeState.PROVIDER_READY
    assert result.credential_status is ProviderCredentialStatus.USABLE
    assert result.provider_session_reference == "codex-session-1"
    assert client.operation is None
    assert not hasattr(result, "credential")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    (
        ProviderCredentialStatus.UNAVAILABLE,
        ProviderCredentialStatus.INVALID,
        ProviderCredentialStatus.EXPIRED,
    ),
)
async def test_runtime_rejects_unusable_credentials_without_provider_call(
    status: ProviderCredentialStatus,
) -> None:
    client = FakeCodexClient()
    provider = CodexExecutionProvider(
        client=client,
        model="codex-test-model",
        implementation_version="1",
    )
    runtime = RegistryProviderRuntime(
        providers=ExecutionProviderRegistry((provider,)),
        credentials=FakeCredentialResolver(status),
    )
    with pytest.raises(ProviderAuthenticationError):
        await runtime.open(
            ProviderRuntimeRequest(
                provider_session_id=uuid4(),
                company_id=uuid4(),
                worker_id=uuid4(),
                provider_identifier="codex",
                capabilities=provider.capabilities,
                expires_at=now() + timedelta(minutes=10),
            )
        )
    assert client.session_request is None
    assert client.operation is None


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
