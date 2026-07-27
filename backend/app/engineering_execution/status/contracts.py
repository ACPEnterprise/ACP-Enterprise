from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class ProjectionAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class MonitoringState(StrEnum):
    NOT_APPROVED = "not_approved"
    APPROVED_NOT_DISPATCHABLE = "approved_not_dispatchable"
    DISCONNECTED = "disconnected"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConnectionState(StrEnum):
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"


class LeasePhase(StrEnum):
    ACTIVE = "active"
    EXPIRING = "expiring"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class CommandStatusSource:
    command_id: UUID
    ecid: str
    approval_state: str
    command_updated_at: datetime
    requested_code_changes: bool = False


@dataclass(frozen=True)
class ExecutionStatusSource:
    execution_id: UUID
    state: str
    status: str
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
    failure_classification: str | None
    validation_available: bool
    evidence_available: bool
    output_reference_count: int


@dataclass(frozen=True)
class LeaseStatusSource:
    lease_id: UUID
    worker_id: UUID
    status: str
    started_at: datetime
    expires_at: datetime
    released_at: datetime | None


@dataclass(frozen=True)
class HeartbeatStatusSource:
    health: str
    last_seen: datetime


@dataclass(frozen=True)
class TransportSessionStatusSource:
    state: str
    established_at: datetime
    expires_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True)
class ResultStatusSource:
    status: str
    failure_classification: str
    validation_available: bool
    evidence_available: bool
    output_reference_count: int
    created_at: datetime


@dataclass(frozen=True)
class ReviewStatusSource:
    review_id: UUID
    state: str
    version: int
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True)
class RepositoryAuthorizationStatusSource:
    authorization_id: UUID
    state: str
    operation_type: str
    authorized_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    consumed_at: datetime | None


@dataclass(frozen=True)
class SupervisorStatusSource:
    supervisor_state: str
    session_state: str | None
    runtime_state: str | None
    credential_status: str
    provider_ready: bool
    ready: bool
    updated_at: datetime
    expires_at: datetime | None
    failure_classification: str | None
    execution_active: bool = False
    command_id: UUID | None = None
    execution_offer_id: UUID | None = None
    provider_session_reference_present: bool = False


@dataclass(frozen=True)
class ExecutionStatusSources:
    command: CommandStatusSource
    execution: ExecutionStatusSource | None
    lease: LeaseStatusSource | None
    heartbeat: HeartbeatStatusSource | None
    transport_session: TransportSessionStatusSource | None
    result: ResultStatusSource | None
    supervisor: SupervisorStatusSource | None = None
    review: ReviewStatusSource | None = None
    repository_authorization: RepositoryAuthorizationStatusSource | None = None


class ExecutionStatusProvider(Protocol):
    async def load(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
    ) -> ExecutionStatusSources | None: ...
