import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from app.execution_providers.codex import (
    CodexClientAuthenticationError,
    CodexClientRequestError,
    CodexClientUnavailableError,
    CodexOperation,
    CodexSessionRequest,
    OpenAIModelsClient,
)
from app.execution_providers.credentials import (
    EnvironmentCredentialResolver,
    ProviderCredentialMaterial,
)
from app.execution_providers.production import (
    CodexProductionConfig,
    CodexProviderFactory,
    ExecutionProviderFactoryRegistry,
)
from app.execution_providers.runtime import (
    ProductionProviderRuntime,
    ProviderCredentialResolution,
    ProviderCredentialResolutionError,
    ProviderCredentialStatus,
    ProviderRuntimeRequest,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def client_for(handler: httpx.AsyncBaseTransport) -> OpenAIModelsClient:
    return OpenAIModelsClient(
        api_key="unit-test-only",
        model="configured-readiness-model",
        transport=handler,
    )


@pytest.mark.asyncio
async def test_models_readiness_uses_one_non_generating_request() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={"id": "configured-readiness-model", "object": "model"},
        )

    client = client_for(httpx.MockTransport(handler))
    result = await client.open_session(
        CodexSessionRequest(uuid4(), "opaque", now() + timedelta(minutes=1))
    )
    await client.close_session(result.session_reference)

    assert requests == [("GET", "/v1/models/configured-readiness-model")]
    assert result.ready is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error"),
    (
        (401, CodexClientAuthenticationError),
        (403, CodexClientRequestError),
        (404, CodexClientRequestError),
        (429, CodexClientUnavailableError),
        (500, CodexClientUnavailableError),
    ),
)
async def test_models_readiness_translates_bounded_failures(
    status: int, error: type[Exception]
) -> None:
    client = client_for(
        httpx.MockTransport(
            lambda request: httpx.Response(
                status, json={"sensitive_provider_diagnostic": "not propagated"}
            )
        )
    )
    with pytest.raises(error) as captured:
        await client.open_session(
            CodexSessionRequest(uuid4(), "opaque", now() + timedelta(minutes=1))
        )
    assert "sensitive_provider_diagnostic" not in str(captured.value)


@pytest.mark.asyncio
async def test_models_readiness_rejects_malformed_metadata() -> None:
    client = client_for(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"object": "unexpected"})
        )
    )
    with pytest.raises(CodexClientRequestError):
        await client.open_session(
            CodexSessionRequest(uuid4(), "opaque", now() + timedelta(minutes=1))
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    (
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("unavailable"),
    ),
)
async def test_models_readiness_translates_transport_failures(error: Exception) -> None:
    client = client_for(
        httpx.MockTransport(lambda request: (_ for _ in ()).throw(error))
    )
    with pytest.raises(CodexClientUnavailableError):
        await client.open_session(
            CodexSessionRequest(uuid4(), "opaque", now() + timedelta(minutes=1))
        )


@pytest.mark.asyncio
async def test_readiness_client_has_no_execution_path() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    client = client_for(httpx.MockTransport(handler))
    with pytest.raises(CodexClientRequestError):
        await client.execute(
            CodexOperation(
                uuid4(),
                "model",
                "prohibited",
                "repository",
                "branch",
                "head",
                False,
                uuid4(),
            )
        )
    assert requests == []


@pytest.mark.asyncio
async def test_environment_credential_is_ephemeral_and_redacted() -> None:
    resolver = EnvironmentCredentialResolver(
        environment={"OPENAI_API_KEY": "unit-test-only"}
    )
    result = await resolver.resolve(
        company_id=uuid4(),
        worker_id=uuid4(),
        provider_identifier="codex",
        now=now(),
    )
    assert result.status is ProviderCredentialStatus.USABLE
    assert isinstance(result.material, ProviderCredentialMaterial)
    assert "unit-test-only" not in repr(result.material)


class RecordingResolver:
    def __init__(self, status: ProviderCredentialStatus) -> None:
        self.status = status

    async def resolve(self, **_: object) -> ProviderCredentialResolution:
        material = (
            ProviderCredentialMaterial("unit-test-only")
            if self.status is ProviderCredentialStatus.USABLE
            else None
        )
        return ProviderCredentialResolution(
            status=self.status,
            credential_reference=(
                "environment:OPENAI_API_KEY"
                if self.status is ProviderCredentialStatus.USABLE
                else None
            ),
            expires_at=None,
            material=material,
        )


def runtime_request() -> ProviderRuntimeRequest:
    factory = CodexProviderFactory(CodexProductionConfig())
    return ProviderRuntimeRequest(
        provider_session_id=uuid4(),
        company_id=uuid4(),
        worker_id=uuid4(),
        provider_identifier="codex",
        capabilities=factory.capabilities,
        expires_at=now() + timedelta(minutes=1),
    )


@pytest.mark.asyncio
async def test_production_runtime_creates_client_only_after_credential_validation() -> (
    None
):
    class RecordingFactory(CodexProviderFactory):
        creates = 0

        def create(self, material: ProviderCredentialMaterial):
            self.creates += 1
            return super().create(material)

    factory = RecordingFactory(CodexProductionConfig())
    runtime = ProductionProviderRuntime(
        factories=ExecutionProviderFactoryRegistry((factory,)),
        credentials=RecordingResolver(ProviderCredentialStatus.UNAVAILABLE),
    )
    with pytest.raises(ProviderCredentialResolutionError):
        await runtime.open(runtime_request())
    assert factory.creates == 0


@pytest.mark.asyncio
async def test_cancelled_readiness_closes_client_without_execution() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        started.set()
        await release.wait()
        return httpx.Response(
            200,
            json={"id": "configured-readiness-model", "object": "model"},
        )

    client = client_for(httpx.MockTransport(handler))
    task = asyncio.create_task(
        client.open_session(
            CodexSessionRequest(uuid4(), "opaque", now() + timedelta(minutes=1))
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await client.close_session("")
    assert len(requests) == 1
