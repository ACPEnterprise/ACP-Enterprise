from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.execution_providers.contracts import ProviderCapability


class SupervisorState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    RECOVERING = "recovering"
    RECONNECTING = "reconnecting"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ProviderSessionState(StrEnum):
    CREATED = "created"
    OPENING = "opening"
    READY = "ready"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    EXPIRED = "expired"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CreateProviderSession:
    composition_id: UUID
    attempt_id: UUID
    timeout_seconds: int


@dataclass(frozen=True)
class RecoveryItem:
    composition_id: UUID
    attempt_id: UUID | None
    composition_state: str
    attempt_state: str | None
    cancellation_requested: bool


@dataclass(frozen=True)
class SupervisorRecovery:
    supervisor_id: UUID
    recovered_at: datetime
    items: tuple[RecoveryItem, ...]


@dataclass(frozen=True)
class CapabilityNegotiation:
    required: tuple[ProviderCapability, ...]
    effective: tuple[ProviderCapability, ...]
    approved_code_changes: bool
