from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol
from uuid import UUID

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
            raise ProviderAuthenticationError("Codex authentication failed.") from error
        except CodexClientUnavailableError as error:
            raise ProviderUnavailableError("Codex is unavailable.") from error
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
