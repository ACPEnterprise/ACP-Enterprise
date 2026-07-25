from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from .contracts import (
    ProviderCapabilities,
    ProviderSessionRequest,
    ProviderSessionStatus,
)
from .errors import ProviderAuthenticationError, ProviderUnavailableError
from .registry import ExecutionProviderRegistry


class ProviderRuntimeState(StrEnum):
    CREATED = "created"
    INITIALIZING = "initializing"
    CREDENTIAL_VALIDATION = "credential_validation"
    PROVIDER_INITIALIZING = "provider_initializing"
    PROVIDER_READY = "provider_ready"
    OPENING = "opening"
    READY = "ready"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    RECOVERING = "recovering"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CREDENTIAL_FAILURE = "credential_failure"
    PROVIDER_FAILURE = "provider_failure"
    TIMEOUT = "timeout"


class ProviderCredentialStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    EXPIRED = "expired"
    USABLE = "usable"


@dataclass(frozen=True)
class ProviderCredentialResolution:
    status: ProviderCredentialStatus
    credential_reference: str | None
    expires_at: datetime | None


class ProviderCredentialResolver(Protocol):
    async def resolve(
        self,
        *,
        company_id: UUID,
        worker_id: UUID,
        provider_identifier: str,
        now: datetime,
    ) -> ProviderCredentialResolution: ...


@dataclass(frozen=True)
class ProviderRuntimeRequest:
    provider_session_id: UUID
    company_id: UUID
    worker_id: UUID
    provider_identifier: str
    capabilities: ProviderCapabilities
    expires_at: datetime
    provider_session_reference: str | None = None


@dataclass(frozen=True)
class ProviderRuntimeResult:
    provider_session_id: UUID
    state: ProviderRuntimeState
    observed_at: datetime
    failure_classification: str | None
    credential_status: ProviderCredentialStatus
    provider_session_reference: str | None


class ProviderRuntime(Protocol):
    """Provider-neutral operational boundary around provider sessions."""

    def capabilities(self, provider_identifier: str) -> ProviderCapabilities:
        """Return only the registered provider's declared capabilities."""

    async def open(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        """Open a future provider session."""

    async def supervise(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        """Observe a future provider session."""

    async def cancel(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        """Request cancellation of a future provider session."""

    async def close(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        """Close a future provider session."""

    async def recover(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        """Recover a future provider session from durable state."""


class RegistryProviderRuntime:
    """Provider-neutral runtime; provider credentials remain resolver-owned."""

    def __init__(
        self,
        *,
        providers: ExecutionProviderRegistry,
        credentials: ProviderCredentialResolver,
    ) -> None:
        self._providers = providers
        self._credentials = credentials

    def capabilities(self, provider_identifier: str) -> ProviderCapabilities:
        return self._providers.capabilities(provider_identifier)

    async def open(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        if request.expires_at <= now:
            raise ProviderUnavailableError("Provider runtime request expired.")
        credential = await self._credentials.resolve(
            company_id=request.company_id,
            worker_id=request.worker_id,
            provider_identifier=request.provider_identifier,
            now=now,
        )
        if (
            credential.status is not ProviderCredentialStatus.USABLE
            or credential.credential_reference is None
            or (credential.expires_at is not None and credential.expires_at <= now)
        ):
            raise ProviderAuthenticationError("Provider credential is unusable.")
        provider = self._providers.resolve(request.provider_identifier)
        result = await provider.open_session(
            ProviderSessionRequest(
                provider_session_id=request.provider_session_id,
                company_id=request.company_id,
                worker_id=request.worker_id,
                provider_identifier=request.provider_identifier,
                capabilities=request.capabilities,
                credential_reference=credential.credential_reference,
                provider_session_reference=None,
                expires_at=request.expires_at,
            )
        )
        if result.status is not ProviderSessionStatus.READY:
            raise ProviderUnavailableError("Provider session did not become ready.")
        return ProviderRuntimeResult(
            provider_session_id=request.provider_session_id,
            state=ProviderRuntimeState.PROVIDER_READY,
            observed_at=result.observed_at,
            failure_classification=None,
            credential_status=ProviderCredentialStatus.USABLE,
            provider_session_reference=result.provider_session_reference,
        )

    async def supervise(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        health = await self._providers.health(request.provider_identifier)
        return ProviderRuntimeResult(
            provider_session_id=request.provider_session_id,
            state=(
                ProviderRuntimeState.ACTIVE
                if health.available
                else ProviderRuntimeState.PROVIDER_FAILURE
            ),
            observed_at=health.checked_at,
            failure_classification=None if health.available else health.status_code,
            credential_status=ProviderCredentialStatus.USABLE,
            provider_session_reference=request.provider_session_reference,
        )

    async def cancel(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        return await self._session_operation(
            request, "cancel", ProviderRuntimeState.CANCELLED
        )

    async def close(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        return await self._session_operation(
            request, "close", ProviderRuntimeState.CLOSED
        )

    async def recover(self, request: ProviderRuntimeRequest) -> ProviderRuntimeResult:
        return await self._session_operation(
            request, "recover", ProviderRuntimeState.PROVIDER_READY
        )

    async def _session_operation(
        self,
        request: ProviderRuntimeRequest,
        operation: str,
        success_state: ProviderRuntimeState,
    ) -> ProviderRuntimeResult:
        if request.provider_session_reference is None:
            raise ProviderUnavailableError("Provider session reference is unavailable.")
        provider = self._providers.resolve(request.provider_identifier)
        provider_request = ProviderSessionRequest(
            provider_session_id=request.provider_session_id,
            company_id=request.company_id,
            worker_id=request.worker_id,
            provider_identifier=request.provider_identifier,
            capabilities=request.capabilities,
            credential_reference=None,
            provider_session_reference=request.provider_session_reference,
            expires_at=request.expires_at,
        )
        if operation == "cancel":
            result = await provider.cancel_session(provider_request)
        elif operation == "close":
            result = await provider.close_session(provider_request)
        else:
            result = await provider.recover_session(provider_request)
        if result.status is ProviderSessionStatus.FAILED:
            raise ProviderUnavailableError("Provider session operation failed.")
        return ProviderRuntimeResult(
            provider_session_id=request.provider_session_id,
            state=success_state,
            observed_at=result.observed_at,
            failure_classification=None,
            credential_status=ProviderCredentialStatus.USABLE,
            provider_session_reference=result.provider_session_reference,
        )
