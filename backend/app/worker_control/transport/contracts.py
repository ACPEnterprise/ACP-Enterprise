from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
    WorkerExecutionResult,
    WorkerHealth,
)


class WorkerSessionState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class TransportMessageKind(StrEnum):
    HEARTBEAT = "heartbeat"
    RESULT = "result"


@dataclass(frozen=True)
class WorkerSessionChallenge:
    challenge_id: UUID
    worker_id: UUID
    challenge: str
    issued_at: datetime
    expires_at: datetime
    key_version: str


@dataclass(frozen=True)
class WorkerSessionRequest:
    challenge_id: UUID
    worker_id: UUID
    challenge: str
    authentication_response: str
    capabilities: tuple[WorkerCapability, ...]


@dataclass(frozen=True)
class WorkerSession:
    session_id: UUID
    context: AuthenticatedWorkerContext
    capabilities: tuple[WorkerCapability, ...]
    key_version: str
    state: WorkerSessionState
    established_at: datetime
    expires_at: datetime
    next_sequence: int


@dataclass(frozen=True)
class HeartbeatMessage:
    health: WorkerHealth


@dataclass(frozen=True)
class ResultMessage:
    lease_id: UUID
    expected_lease_version: int
    capability: WorkerCapability
    correlation_id: UUID
    result: WorkerExecutionResult


TransportPayload = HeartbeatMessage | ResultMessage


@dataclass(frozen=True)
class AuthenticatedMessageEnvelope:
    message_id: UUID
    session_id: UUID
    worker_id: UUID
    sequence_number: int
    sent_at: datetime
    kind: TransportMessageKind
    payload: TransportPayload
    authentication_proof: str
    key_version: str


@dataclass(frozen=True)
class TransportReceipt:
    message_id: UUID
    sequence_number: int
    accepted_at: datetime
    duplicate: bool
    outcome_reference: str


class WorkerMessageAuthenticator(Protocol):
    """Provider-neutral authentication seam; implementations own cryptography."""

    @property
    def active_key_version(self) -> str: ...

    async def authenticate_challenge_response(
        self,
        *,
        worker_id: UUID,
        authentication_response: str,
        key_version: str,
        now: datetime,
    ) -> AuthenticatedWorkerContext: ...

    async def verify_message(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> bool: ...
