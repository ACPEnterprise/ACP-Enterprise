from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class OfferPageResponse(StrictModel):
    items: tuple[OfferResponse, ...]
    retry_after_seconds: int
