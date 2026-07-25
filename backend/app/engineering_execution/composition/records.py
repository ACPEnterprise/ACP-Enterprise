from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from uuid import UUID

from app.engineering_execution.composition.contracts import (
    CompositionIntegrityEvidence,
    CompositionReceiptStatus,
    CompositionState,
    ProviderAttemptState,
    ProviderProgressPhase,
    ProviderResultDisposition,
    ProviderResultStatus,
)


@dataclass(frozen=True)
class CreateExecutionComposition:
    company_id: UUID
    command_id: UUID
    execution_id: UUID
    worker_id: UUID
    lease_id: UUID
    provider_identifier: str
    required_capabilities: tuple[str, ...]
    effective_capabilities: tuple[str, ...]
    approved_code_changes: bool
    repository_key: str
    expected_branch: str
    expected_head: str
    instruction_digest: str
    request_digest: str
    expires_at: datetime
    composition_digest: str
    created_at: datetime


@dataclass(frozen=True)
class ExecutionCompositionRecord:
    id: UUID
    company_id: UUID
    command_id: UUID
    execution_id: UUID
    worker_id: UUID
    lease_id: UUID
    provider_identifier: str
    required_capabilities: tuple[str, ...]
    effective_capabilities: tuple[str, ...]
    approved_code_changes: bool
    repository_key: str
    expected_branch: str
    expected_head: str
    instruction_digest: str
    request_digest: str
    expires_at: datetime
    composition_digest: str
    state: CompositionState
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CompositionReceiptRecord:
    id: UUID
    composition_id: UUID
    company_id: UUID
    execution_id: UUID
    worker_id: UUID
    lease_id: UUID
    provider_identifier: str
    instruction_digest: str
    request_digest: str
    composition_digest: str
    status: CompositionReceiptStatus
    created_at: datetime
    expires_at: datetime
    version: int
    integrity: CompositionIntegrityEvidence


@dataclass(frozen=True)
class CompositionBundle:
    composition: ExecutionCompositionRecord
    receipt: CompositionReceiptRecord


@dataclass(frozen=True)
class CompositionDeliveryPackage:
    composition: ExecutionCompositionRecord
    receipt: CompositionReceiptRecord
    instruction: str


@dataclass(frozen=True)
class PrepareProviderAttempt:
    company_id: UUID
    composition_id: UUID
    worker_id: UUID
    lease_id: UUID
    provider_identifier: str
    idempotency_key: UUID
    prepared_at: datetime


@dataclass(frozen=True)
class ProviderExecutionAttemptRecord:
    id: UUID
    company_id: UUID
    composition_id: UUID
    worker_id: UUID
    lease_id: UUID
    provider_identifier: str
    attempt_ordinal: int
    idempotency_key: UUID
    state: ProviderAttemptState
    version: int
    prepared_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    failure_classification: str | None
    cancellation_requested_at: datetime | None
    cancellation_acknowledged_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AppendProviderProgress:
    company_id: UUID
    attempt_id: UUID
    phase: ProviderProgressPhase
    message_code: str
    summary: str | None
    percentage: int | None
    created_at: datetime


@dataclass(frozen=True)
class ProviderProgressEventRecord:
    id: UUID
    company_id: UUID
    attempt_id: UUID
    sequence_number: int
    phase: ProviderProgressPhase
    message_code: str
    summary: str | None
    percentage: int | None
    created_at: datetime


@dataclass(frozen=True)
class StoreProviderResult:
    company_id: UUID
    attempt_id: UUID
    composition_id: UUID
    status: ProviderResultStatus
    evidence_summary: dict[str, object]
    validation_summary: dict[str, object]
    output_references: tuple[str, ...]
    failure_classification: str | None
    received_at: datetime
    disposition: ProviderResultDisposition
    disposition_reason: str | None


@dataclass(frozen=True)
class NormalizedProviderResultRecord:
    id: UUID
    company_id: UUID
    attempt_id: UUID
    composition_id: UUID
    status: ProviderResultStatus
    evidence_summary: Mapping[str, object]
    validation_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_classification: str | None
    repository_mutated: bool
    received_at: datetime
    disposition: ProviderResultDisposition
    disposition_reason: str | None
    created_at: datetime
