from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from app.worker_control.contracts import WorkerCapability


class ControlledCommandType(StrEnum):
    INSPECT_WORKSPACE = "inspect_workspace"
    EXECUTE_CODE = "execute_code"


class ControlledOfferState(StrEnum):
    AVAILABLE = "available"
    ACQUIRED = "acquired"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ControlledOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ControlledExecutionOffer:
    id: UUID
    company_id: UUID
    command_id: UUID
    execution_id: UUID
    correlation_id: UUID
    workspace_id: str
    command_type: ControlledCommandType
    payload: Mapping[str, object]
    capability_required: WorkerCapability
    state: ControlledOfferState
    expires_at: datetime
    lease_seconds: int
    lease_id: UUID | None
    worker_id: UUID | None
    session_id: UUID | None
    version: int
    created_at: datetime
    acquired_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class ControlledExecutionResult:
    id: UUID
    company_id: UUID
    offer_id: UUID
    command_id: UUID
    execution_id: UUID
    lease_id: UUID
    worker_id: UUID
    session_id: UUID
    outcome: ControlledOutcome
    output: Mapping[str, object]
    error_classification: str | None
    repository_mutated: bool
    correlation_id: UUID
    started_at: datetime
    completed_at: datetime
    created_at: datetime


def immutable_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))
