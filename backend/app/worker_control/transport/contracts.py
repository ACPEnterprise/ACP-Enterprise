from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_execution.composition.contracts import (
    ProviderProgressPhase,
    ProviderResultStatus,
)
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
    LEASE_RENEWAL = "lease_renewal"
    COMPOSITION_FETCH = "composition_fetch"
    COMPOSITION_ACKNOWLEDGEMENT = "composition_acknowledgement"
    PROVIDER_PROGRESS = "provider_progress"
    PROVIDER_RESULT = "provider_result"
    CANCELLATION_ACKNOWLEDGEMENT = "cancellation_acknowledgement"
    CONTROLLED_OFFER_ACQUISITION = "controlled_offer_acquisition"
    CONTROLLED_EXECUTION_RESULT = "controlled_execution_result"
    WORKSTREAM_ACKNOWLEDGEMENT = "workstream_acknowledgement"
    WORKSTREAM_RUNTIME_UPDATE = "workstream_runtime_update"


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
    worker_identity_id: UUID | None
    credential_id: UUID | None
    credential_version: int | None
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


@dataclass(frozen=True)
class LeaseRenewalMessage:
    lease_id: UUID
    expected_lease_version: int
    lease_seconds: int


@dataclass(frozen=True)
class CompositionFetchMessage:
    pass


@dataclass(frozen=True)
class CompositionAcknowledgementMessage:
    composition_id: UUID
    composition_digest: str
    instruction_digest: str
    request_digest: str


@dataclass(frozen=True)
class ProviderProgressMessage:
    attempt_id: UUID
    lease_id: UUID
    composition_digest: str
    instruction_digest: str
    request_digest: str
    phase: ProviderProgressPhase
    message_code: str
    summary: str | None = None
    percentage: int | None = None


@dataclass(frozen=True)
class ProviderResultMessage:
    attempt_id: UUID
    lease_id: UUID
    composition_digest: str
    instruction_digest: str
    request_digest: str
    status: ProviderResultStatus
    evidence_summary: dict[str, object]
    validation_summary: dict[str, object]
    output_references: tuple[str, ...]
    failure_classification: str | None = None
    repository_mutated: bool = False


@dataclass(frozen=True)
class CancellationAcknowledgementMessage:
    attempt_id: UUID
    lease_id: UUID
    expected_version: int
    composition_digest: str


@dataclass(frozen=True)
class ControlledOfferAcquisitionMessage:
    offer_id: UUID


@dataclass(frozen=True)
class ControlledExecutionResultMessage:
    offer_id: UUID
    lease_id: UUID
    outcome: str
    output: dict[str, object]
    error_classification: str | None
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class WorkstreamAcknowledgementMessage:
    control_id: UUID
    expected_control_version: int
    action: str
    idempotency_key: str
    reason_code: str | None


@dataclass(frozen=True)
class WorkstreamRuntimeUpdateMessage:
    command_id: UUID
    expected_runtime_version: int
    runtime_state: str
    worker_health: str
    progress_percent: int | None
    current_activity: str | None
    reason_code: str | None
    idempotency_key: str


TransportPayload = (
    HeartbeatMessage
    | ResultMessage
    | LeaseRenewalMessage
    | CompositionFetchMessage
    | CompositionAcknowledgementMessage
    | ProviderProgressMessage
    | ProviderResultMessage
    | CancellationAcknowledgementMessage
    | ControlledOfferAcquisitionMessage
    | ControlledExecutionResultMessage
    | WorkstreamAcknowledgementMessage
    | WorkstreamRuntimeUpdateMessage
)


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


@dataclass(frozen=True)
class AuthenticatedWorkerSessionIdentity:
    context: AuthenticatedWorkerContext
    worker_identity_id: UUID
    credential_id: UUID
    credential_version: int


class WorkerMessageAuthenticator(Protocol):
    """Provider-neutral authentication seam; implementations own cryptography."""

    async def active_key_version(
        self, database: AsyncSession, *, worker_id: UUID, now: datetime
    ) -> str: ...

    async def authenticate_challenge_response(
        self,
        database: AsyncSession,
        *,
        worker_id: UUID,
        challenge: str,
        authentication_response: str,
        key_version: str,
        now: datetime,
    ) -> AuthenticatedWorkerSessionIdentity: ...

    async def validate_session(
        self,
        database: AsyncSession,
        *,
        session: WorkerSession,
        now: datetime,
    ) -> None: ...

    async def verify_message(
        self,
        database: AsyncSession,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> bool: ...
