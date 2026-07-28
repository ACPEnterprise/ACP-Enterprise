from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID


class EngineeringExecutionState(StrEnum):
    EXECUTION_NOT_CONNECTED = "execution_not_connected"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EngineeringExecutionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EngineeringFailureClassification(StrEnum):
    PROVIDER_NOT_CONNECTED = "provider_not_connected"
    CONTROLLED_EXECUTION_FAILED = "controlled_execution_failed"


@dataclass(frozen=True)
class EngineeringExecutionRequest:
    command_id: UUID
    ecid: str
    repository_key: str
    expected_repository_baseline: str
    expected_branch: str
    expected_head: str
    authorized_code_changes: bool
    instruction: str
    instruction_digest: str
    request_digest: str
    correlation_id: UUID


@dataclass(frozen=True)
class EngineeringExecutionResult:
    execution_id: UUID
    state: EngineeringExecutionState
    status: EngineeringExecutionStatus
    started_at: datetime | None
    finished_at: datetime | None
    provider_identifier: str
    evidence_summary: Mapping[str, object]
    validation_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_classification: EngineeringFailureClassification | None


def immutable_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))
