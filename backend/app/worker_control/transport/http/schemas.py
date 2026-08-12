from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.engineering_execution.composition.contracts import (
    ProviderProgressPhase,
    ProviderResultStatus,
)
from app.worker_control.contracts import (
    WorkerCapability,
    WorkerFailureClassification,
    WorkerHealth,
    WorkerResultStatus,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChallengeResponse(StrictModel):
    challenge_id: UUID
    worker_id: UUID
    challenge: str
    issued_at: datetime
    expires_at: datetime
    key_version: str


class EstablishSessionRequest(StrictModel):
    challenge_id: UUID
    challenge: str
    authentication_response: Annotated[str, Field(min_length=1, max_length=4096)]
    capabilities: tuple[WorkerCapability, ...]


class SessionResponse(StrictModel):
    session_id: UUID
    worker_id: UUID
    capabilities: tuple[WorkerCapability, ...]
    key_version: str
    state: str
    established_at: datetime
    expires_at: datetime
    next_sequence: int


class EnvelopeEvidence(StrictModel):
    message_id: UUID
    session_id: UUID
    sequence_number: Annotated[int, Field(ge=1)]
    sent_at: datetime
    authentication_proof: Annotated[str, Field(min_length=1, max_length=4096)]
    key_version: Annotated[str, Field(min_length=1, max_length=100)]


class HeartbeatRequest(EnvelopeEvidence):
    health: WorkerHealth


class RepositoryReadinessTarget(StrictModel):
    milestone_id: UUID
    repository_key: str
    branch: str
    candidate_head: str


class RepositoryReadinessTargetPage(StrictModel):
    items: tuple[RepositoryReadinessTarget, ...]


class RepositoryReadinessRequest(EnvelopeEvidence):
    milestone_id: UUID
    repository_key: Annotated[str, Field(min_length=1, max_length=100)]
    branch: Annotated[str, Field(min_length=1, max_length=255)]
    candidate_head: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    observed_head: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    provider_software_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    prepared_at: datetime
    ready: bool
    reason_code: Annotated[str | None, Field(max_length=100)] = None


class LeaseRenewalRequest(EnvelopeEvidence):
    lease_id: UUID
    expected_lease_version: Annotated[int, Field(ge=1)]
    lease_seconds: Annotated[int, Field(ge=30, le=900)]


class ResultRequest(EnvelopeEvidence):
    lease_id: UUID
    expected_lease_version: Annotated[int, Field(ge=1)]
    capability: WorkerCapability
    correlation_id: UUID
    execution_id: UUID
    status: Literal[WorkerResultStatus.NOT_EXECUTED]
    failure_classification: Literal[WorkerFailureClassification.EXECUTION_NOT_CONNECTED]
    repository_mutated: Literal[False]


class CompositionFetchRequest(EnvelopeEvidence):
    pass


class CompositionAcknowledgementRequest(EnvelopeEvidence):
    composition_id: UUID
    composition_digest: Annotated[str, Field(min_length=64, max_length=64)]
    instruction_digest: Annotated[str, Field(min_length=64, max_length=128)]
    request_digest: Annotated[str, Field(min_length=64, max_length=128)]


class ProviderProgressRequest(CompositionAcknowledgementRequest):
    attempt_id: UUID
    lease_id: UUID
    phase: ProviderProgressPhase
    message_code: Annotated[str, Field(min_length=1, max_length=100)]
    summary: Annotated[str | None, Field(max_length=500)] = None
    percentage: Annotated[int | None, Field(ge=0, le=100)] = None


class ProviderNormalizedResultRequest(CompositionAcknowledgementRequest):
    attempt_id: UUID
    lease_id: UUID
    status: ProviderResultStatus
    evidence_summary: dict[str, object] = Field(default_factory=dict)
    validation_summary: dict[str, object] = Field(default_factory=dict)
    output_references: Annotated[tuple[str, ...], Field(max_length=20)] = ()
    failure_classification: Annotated[str | None, Field(max_length=100)] = None
    repository_mutated: Literal[False]


class CancellationAcknowledgementRequest(EnvelopeEvidence):
    attempt_id: UUID
    lease_id: UUID
    expected_version: Annotated[int, Field(ge=1)]
    composition_digest: Annotated[str, Field(min_length=64, max_length=64)]


class ControlledOfferAcquisitionRequest(EnvelopeEvidence):
    offer_id: UUID


class ControlledExecutionResultRequest(EnvelopeEvidence):
    offer_id: UUID
    lease_id: UUID
    outcome: Literal["succeeded", "failed", "timed_out", "cancelled"]
    output: dict[str, object]
    error_classification: Annotated[str | None, Field(max_length=80)] = None
    started_at: datetime
    completed_at: datetime


class WorkstreamAcknowledgementRequest(EnvelopeEvidence):
    control_id: UUID
    expected_control_version: Annotated[int, Field(ge=1)]
    action: Literal["start", "pause", "resume", "cancel"]
    idempotency_key: Annotated[str, Field(min_length=1, max_length=128)]
    reason_code: Annotated[str | None, Field(max_length=100)] = None


class WorkstreamRuntimeUpdateRequest(EnvelopeEvidence):
    command_id: UUID
    expected_runtime_version: Annotated[int, Field(ge=1)]
    runtime_state: Literal[
        "queued",
        "acknowledged",
        "running",
        "paused",
        "waiting_for_owner",
        "validating",
        "deploying_preview",
        "completed",
        "failed",
        "cancelled",
        "recovering",
    ]
    worker_health: Annotated[str, Field(min_length=1, max_length=24)]
    progress_percent: Annotated[int | None, Field(ge=0, le=100)] = None
    current_activity: Annotated[str | None, Field(max_length=240)] = None
    reason_code: Annotated[str | None, Field(max_length=100)] = None
    idempotency_key: Annotated[str, Field(min_length=1, max_length=128)]


class PendingWorkstreamControl(StrictModel):
    control_id: UUID
    command_id: UUID
    action: str
    desired_state: str
    version: int
    reason: str | None
    requested_at: datetime


class PendingWorkstreamControlPage(StrictModel):
    items: tuple[PendingWorkstreamControl, ...]


class ReceiptResponse(StrictModel):
    message_id: UUID
    sequence_number: int
    accepted_at: datetime
    duplicate: bool
    outcome_reference: str


class OfferResponse(StrictModel):
    offer_id: UUID
    execution_id: UUID
    correlation_id: UUID
    capability_required: WorkerCapability
    lease_seconds: int
    expires_at: datetime
    command_id: UUID
    workspace_id: str
    command_type: Literal["inspect_workspace", "execute_code"]
    payload: dict[str, object]


class ControlledOfferAcquisitionResponse(StrictModel):
    receipt: ReceiptResponse
    offer_id: UUID
    lease_id: UUID
    lease_version: int
    workspace_id: str
    command_type: Literal["inspect_workspace", "execute_code"]
    payload: dict[str, object]


class OfferPageResponse(StrictModel):
    items: tuple[OfferResponse, ...]
    retry_after_seconds: int


class CompositionDeliveryResponse(StrictModel):
    composition_id: UUID
    execution_id: UUID
    lease_id: UUID
    provider_identifier: str
    required_capabilities: tuple[str, ...]
    effective_capabilities: tuple[str, ...]
    approved_code_changes: bool
    repository_key: str
    expected_branch: str
    expected_head: str
    instruction: str
    instruction_digest: str
    request_digest: str
    composition_digest: str
    expires_at: datetime
    integrity_method: str


class CompositionFetchResponse(StrictModel):
    receipt: ReceiptResponse
    composition: CompositionDeliveryResponse | None
