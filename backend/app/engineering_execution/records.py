from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from uuid import UUID

from app.engineering_execution.contracts import (
    EngineeringExecutionState,
    EngineeringExecutionStatus,
    EngineeringFailureClassification,
)


@dataclass(frozen=True)
class CreateEngineeringExecution:
    company_id: UUID
    command_id: UUID
    ecid: str
    instruction_digest: str
    requested_by_user_id: UUID
    provider_identifier: str
    correlation_id: UUID
    requested_at: datetime
    evidence_summary: dict[str, object]
    validation_summary: dict[str, object]


@dataclass(frozen=True)
class EngineeringExecutionRecord:
    id: UUID
    company_id: UUID
    command_id: UUID
    ecid: str
    instruction_digest: str
    requested_by_user_id: UUID
    provider_identifier: str
    state: EngineeringExecutionState
    status: EngineeringExecutionStatus
    correlation_id: UUID
    evidence_summary: Mapping[str, object]
    validation_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_classification: EngineeringFailureClassification
    version: int
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
