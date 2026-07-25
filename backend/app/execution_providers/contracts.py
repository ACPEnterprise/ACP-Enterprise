from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID


class ProviderCapability(StrEnum):
    ENGINEERING_EXECUTE = "engineering.execute"
    VALIDATION_RUN = "validation.run"


class ProviderExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProviderSessionStatus(StrEnum):
    READY = "ready"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ProviderFailureClassification(StrEnum):
    AUTHENTICATION_FAILED = "authentication_failed"
    CAPABILITY_MISMATCH = "capability_mismatch"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    REQUEST_REJECTED = "request_rejected"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class ProviderIdentity:
    identifier: str
    display_name: str
    implementation_version: str


@dataclass(frozen=True)
class ProviderCapabilities:
    values: tuple[ProviderCapability, ...]

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.values


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    checked_at: datetime
    status_code: str


@dataclass(frozen=True)
class ProviderSessionRequest:
    provider_session_id: UUID
    company_id: UUID
    worker_id: UUID
    provider_identifier: str
    capabilities: ProviderCapabilities
    credential_reference: str | None
    provider_session_reference: str | None
    expires_at: datetime


@dataclass(frozen=True)
class ProviderSessionResult:
    provider_session_id: UUID
    provider_session_reference: str | None
    provider_identifier: str
    status: ProviderSessionStatus
    observed_at: datetime
    failure_classification: ProviderFailureClassification | None


@dataclass(frozen=True)
class ProviderExecutionRequest:
    provider_request_id: UUID
    execution_id: UUID
    lease_id: UUID
    company_id: UUID
    worker_id: UUID
    provider_identifier: str
    repository_key: str
    expected_branch: str
    expected_head: str
    authorized_code_changes: bool
    instruction: str
    instruction_digest: str
    request_digest: str
    correlation_id: UUID


@dataclass(frozen=True)
class ProviderExecutionResult:
    provider_request_id: UUID
    execution_id: UUID
    provider_execution_id: str
    provider_identifier: str
    status: ProviderExecutionStatus
    started_at: datetime
    finished_at: datetime
    evidence_summary: Mapping[str, object]
    validation_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_classification: ProviderFailureClassification | None


def immutable_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


class ExecutionProvider(ABC):
    @property
    @abstractmethod
    def identity(self) -> ProviderIdentity:
        """Return stable provider identity without provider-specific types."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return the provider-neutral capability claim."""

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Check readiness without starting execution."""

    async def open_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        """Establish a provider session without submitting execution."""
        raise NotImplementedError

    async def close_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        """Close an established provider session."""
        raise NotImplementedError

    async def cancel_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        """Propagate cancellation without asserting provider termination."""
        raise NotImplementedError

    async def recover_session(
        self, request: ProviderSessionRequest
    ) -> ProviderSessionResult:
        """Prepare recovery of an established provider session."""
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self, request: ProviderExecutionRequest
    ) -> ProviderExecutionResult:
        """Execute one idempotently identified provider request."""
