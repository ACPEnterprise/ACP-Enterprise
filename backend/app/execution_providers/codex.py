from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx

from app.execution_providers.contracts import (
    ExecutionProvider,
    ProviderCapabilities,
    ProviderCapability,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderFailureClassification,
    ProviderHealth,
    ProviderIdentity,
    ProviderSessionRequest,
    ProviderSessionResult,
    ProviderSessionStatus,
    immutable_mapping,
)
from app.execution_providers.errors import (
    ProviderAuthenticationError,
    ProviderRequestError,
    ProviderUnavailableError,
)


@dataclass(frozen=True)
class CodexOperation:
    idempotency_key: UUID
    model: str
    instruction: str
    repository_key: str
    expected_branch: str
    expected_head: str
    allow_code_changes: bool
    correlation_id: UUID


@dataclass(frozen=True)
class CodexOperationResult:
    operation_id: str
    succeeded: bool
    started_at: datetime
    finished_at: datetime
    evidence_summary: Mapping[str, object]
    validation_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_code: str | None = None


@dataclass(frozen=True)
class CodexSessionRequest:
    session_id: UUID
    credential_reference: str
    expires_at: datetime


@dataclass(frozen=True)
class CodexSessionResult:
    session_reference: str
    ready: bool
    observed_at: datetime
    failure_code: str | None = None


class CodexClient(Protocol):
    """Injected Codex client boundary; credentials never enter domain contracts."""

    async def health(self) -> ProviderHealth: ...

    async def open_session(
        self, request: CodexSessionRequest
    ) -> CodexSessionResult: ...

    async def close_session(self, session_reference: str) -> CodexSessionResult: ...

    async def cancel_session(self, session_reference: str) -> CodexSessionResult: ...

    async def recover_session(self, session_reference: str) -> CodexSessionResult: ...

    async def execute(self, operation: CodexOperation) -> CodexOperationResult: ...


class CodexClientAuthenticationError(Exception):
    pass


class CodexClientUnavailableError(Exception):
    pass


class CodexClientRequestError(Exception):
    pass


class OpenAIModelsClient:
    """OpenAI-specific readiness client; it implements no generation endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not model.strip():
            raise ValueError("OpenAI credential and readiness model are required.")
        self._model = model.strip()
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )
        self._closed = False

    async def health(self) -> ProviderHealth:
        return ProviderHealth(not self._closed, datetime.now().astimezone(), "ready")

    async def open_session(self, request: CodexSessionRequest) -> CodexSessionResult:
        del request
        try:
            response = await self._client.get(
                f"/v1/models/{quote(self._model, safe='')}"
            )
        except httpx.TimeoutException as error:
            raise CodexClientUnavailableError("OpenAI readiness timed out.") from error
        except httpx.HTTPError as error:
            raise CodexClientUnavailableError("OpenAI is unavailable.") from error
        if response.status_code == 401:
            raise CodexClientAuthenticationError("OpenAI authentication failed.")
        if response.status_code in {403, 404}:
            raise CodexClientRequestError("Configured model is inaccessible.")
        if response.status_code == 429 or response.status_code >= 500:
            raise CodexClientUnavailableError("OpenAI readiness is unavailable.")
        if response.status_code != 200:
            raise CodexClientRequestError("OpenAI rejected readiness verification.")
        try:
            payload = response.json()
        except ValueError as error:
            raise CodexClientRequestError(
                "OpenAI returned invalid model metadata."
            ) from error
        if payload.get("object") != "model" or payload.get("id") != self._model:
            raise CodexClientRequestError("OpenAI returned unexpected model metadata.")
        return CodexSessionResult(
            session_reference=f"openai-readiness-{uuid4()}",
            ready=True,
            observed_at=datetime.now().astimezone(),
        )

    async def close_session(self, session_reference: str) -> CodexSessionResult:
        await self._client.aclose()
        self._closed = True
        return CodexSessionResult(session_reference, True, datetime.now().astimezone())

    async def cancel_session(self, session_reference: str) -> CodexSessionResult:
        await self._client.aclose()
        self._closed = True
        return CodexSessionResult(session_reference, True, datetime.now().astimezone())

    async def recover_session(self, session_reference: str) -> CodexSessionResult:
        return CodexSessionResult(session_reference, False, datetime.now().astimezone())

    async def execute(self, operation: CodexOperation) -> CodexOperationResult:
        del operation
        raise CodexClientRequestError(
            "Provider execution is unavailable in the readiness client."
        )


class CodexExecutionProvider(ExecutionProvider):
    def __init__(
        self,
        *,
        client: CodexClient,
        model: str,
        implementation_version: str,
    ) -> None:
        if not model.strip() or not implementation_version.strip():
            raise ValueError("Codex model and implementation version are required.")
        self._client = client
        self._model = model.strip()
        self._identity = ProviderIdentity(
            identifier="codex",
            display_name="Codex",
            implementation_version=implementation_version.strip(),
        )
        self._capabilities = ProviderCapabilities(
            values=(
                ProviderCapability.ENGINEERING_EXECUTE,
                ProviderCapability.VALIDATION_RUN,
            )
        )

    @property
    def identity(self) -> ProviderIdentity:
        return self._identity

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def health(self) -> ProviderHealth:
        return await self._client.health()

    async def open_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        if request.provider_identifier != self.identity.identifier:
            raise ProviderAuthenticationError("Provider session identity mismatch.")
        try:
            response = await self._client.open_session(
                CodexSessionRequest(
                    session_id=request.provider_session_id,
                    credential_reference=request.credential_reference or "",
                    expires_at=request.expires_at,
                )
            )
        except CodexClientAuthenticationError as error:
            await self._client.close_session("")
            raise ProviderAuthenticationError("Codex authentication failed.") from error
        except CodexClientUnavailableError as error:
            await self._client.close_session("")
            raise ProviderUnavailableError("Codex is unavailable.") from error
        except CodexClientRequestError as error:
            await self._client.close_session("")
            raise ProviderRequestError("Codex rejected session readiness.") from error
        except BaseException:
            await self._client.close_session("")
            raise
        return self._session_result(request, response)

    async def close_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        response = await self._client.close_session(
            request.provider_session_reference or ""
        )
        return self._session_result(request, response, ProviderSessionStatus.CLOSED)

    async def cancel_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        response = await self._client.cancel_session(
            request.provider_session_reference or ""
        )
        return self._session_result(request, response, ProviderSessionStatus.CANCELLED)

    async def recover_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        response = await self._client.recover_session(
            request.provider_session_reference or ""
        )
        return self._session_result(request, response)

    def _session_result(
        self,
        request: ProviderSessionRequest,
        response: CodexSessionResult,
        success_status: ProviderSessionStatus = ProviderSessionStatus.READY,
    ) -> ProviderSessionResult:
        return ProviderSessionResult(
            provider_session_id=request.provider_session_id,
            provider_session_reference=response.session_reference,
            provider_identifier=self.identity.identifier,
            status=(success_status if response.ready else ProviderSessionStatus.FAILED),
            observed_at=response.observed_at,
            failure_classification=(
                None
                if response.ready
                else ProviderFailureClassification.PROVIDER_UNAVAILABLE
            ),
        )

    async def execute(
        self, request: ProviderExecutionRequest
    ) -> ProviderExecutionResult:
        if request.provider_identifier != self.identity.identifier:
            raise ProviderAuthenticationError(
                "Provider request identity does not match Codex."
            )
        operation = CodexOperation(
            idempotency_key=request.provider_request_id,
            model=self._model,
            instruction=request.instruction,
            repository_key=request.repository_key,
            expected_branch=request.expected_branch,
            expected_head=request.expected_head,
            allow_code_changes=request.authorized_code_changes,
            correlation_id=request.correlation_id,
        )
        try:
            response = await self._client.execute(operation)
        except CodexClientAuthenticationError as error:
            raise ProviderAuthenticationError("Codex authentication failed.") from error
        except CodexClientUnavailableError as error:
            raise ProviderUnavailableError("Codex is unavailable.") from error
        except CodexClientRequestError as error:
            raise ProviderRequestError("Codex rejected the request.") from error
        return ProviderExecutionResult(
            provider_request_id=request.provider_request_id,
            execution_id=request.execution_id,
            provider_execution_id=response.operation_id,
            provider_identifier=self.identity.identifier,
            status=(
                ProviderExecutionStatus.SUCCEEDED
                if response.succeeded
                else ProviderExecutionStatus.FAILED
            ),
            started_at=response.started_at,
            finished_at=response.finished_at,
            evidence_summary=immutable_mapping(response.evidence_summary),
            validation_summary=immutable_mapping(response.validation_summary),
            output_references=response.output_references,
            failure_classification=(
                None
                if response.succeeded
                else ProviderFailureClassification.PROVIDER_ERROR
            ),
        )
