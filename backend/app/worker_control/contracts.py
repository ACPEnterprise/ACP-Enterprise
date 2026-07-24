from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID


class WorkerLifecycleState(StrEnum):
    REGISTERED = "registered"
    AVAILABLE = "available"
    LEASED = "leased"
    OFFLINE = "offline"
    DISABLED = "disabled"


class WorkerCapability(StrEnum):
    ENGINEERING_EXECUTE = "engineering.execute"
    REVIEW_PACKAGE = "review.package"
    VALIDATION_RUN = "validation.run"


class WorkerHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class WorkerLeaseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"


class WorkerResultStatus(StrEnum):
    NOT_EXECUTED = "not_executed"


class WorkerFailureClassification(StrEnum):
    EXECUTION_NOT_CONNECTED = "execution_not_connected"


@dataclass(frozen=True)
class AuthenticatedWorkerContext:
    company_id: UUID
    worker_id: UUID
    provider_identifier: str
    authentication_subject: str
    authenticated_at: datetime


@dataclass(frozen=True)
class ExecutionOffer:
    offer_id: UUID
    execution_id: UUID
    correlation_id: UUID
    capability_required: WorkerCapability
    lease_duration: timedelta
    expires_at: datetime
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class WorkerExecutionResult:
    execution_id: UUID
    worker_id: UUID
    status: WorkerResultStatus
    validation_summary: Mapping[str, object]
    evidence_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_classification: WorkerFailureClassification


def immutable_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))
