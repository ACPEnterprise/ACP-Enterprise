from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from .contracts import ProviderCapabilities


class ProviderRuntimeState(StrEnum):
    OPENING = "opening"
    READY = "ready"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    RECOVERING = "recovering"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ProviderRuntimeRequest:
    provider_session_id: UUID
    provider_identifier: str
    capabilities: ProviderCapabilities
    expires_at: datetime


@dataclass(frozen=True)
class ProviderRuntimeResult:
    provider_session_id: UUID
    state: ProviderRuntimeState
    observed_at: datetime
    failure_classification: str | None


class ProviderRuntime(Protocol):
    """Future provider-session operations; DF.8B.3 supplies no implementation."""

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
