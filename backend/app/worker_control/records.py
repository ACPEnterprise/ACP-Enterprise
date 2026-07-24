from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from uuid import UUID

from app.worker_control.contracts import (
    WorkerCapability,
    WorkerFailureClassification,
    WorkerHealth,
    WorkerLeaseStatus,
    WorkerLifecycleState,
    WorkerResultStatus,
)


@dataclass(frozen=True)
class RegisterWorker:
    company_id: UUID
    provider_identifier: str
    name: str
    worker_version: str
    capabilities: tuple[WorkerCapability, ...]
    registered_by_user_id: UUID
    registered_at: datetime


@dataclass(frozen=True)
class WorkerIdentity:
    id: UUID
    company_id: UUID
    provider_identifier: str
    name: str
    worker_version: str
    capabilities: tuple[WorkerCapability, ...]
    registered_at: datetime
    last_heartbeat_at: datetime | None
    lifecycle_state: WorkerLifecycleState
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkerLeaseRecord:
    id: UUID
    company_id: UUID
    worker_id: UUID
    execution_id: UUID
    capability_required: WorkerCapability
    started_at: datetime
    expires_at: datetime
    released_at: datetime | None
    status: WorkerLeaseStatus
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkerHeartbeatRecord:
    id: UUID
    company_id: UUID
    worker_id: UUID
    last_seen: datetime
    health: WorkerHealth
    worker_version: int
    created_at: datetime


@dataclass(frozen=True)
class WorkerResultRecord:
    id: UUID
    company_id: UUID
    lease_id: UUID
    worker_id: UUID
    execution_id: UUID
    status: WorkerResultStatus
    validation_summary: Mapping[str, object]
    evidence_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_classification: WorkerFailureClassification
    correlation_id: UUID
    created_at: datetime
