from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidenceLevel,
    BeaconExpirationPolicy,
    BeaconLifecycleAction,
    BeaconLifecycleStatus,
    BeaconPriorityBand,
    BeaconRankingFactorAvailability,
    BeaconSeverity,
    BeaconSignalSource,
)


class BeaconConfidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: BeaconConfidenceLevel
    basis: str


class BeaconEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: UUID
    event_id: UUID | None
    event_type: str | None
    occurred_at: datetime | None


class BeaconSupportingFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value: str | int | bool
    source: str
    measured_at: datetime
    evidence: tuple[BeaconEvidenceResponse, ...]
    unit: str | None


class BeaconRankingFactorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value: str | int | bool | None
    unit: str | None
    availability: BeaconRankingFactorAvailability
    contribution: int
    explanation: str


class BeaconPriorityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    band: BeaconPriorityBand
    score: int
    rank: int
    ranking_factors: tuple[BeaconRankingFactorResponse, ...]
    explanation: str
    evaluated_at: datetime
    tie_break_semantics: str


class BeaconLifecycleEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condition_key: UUID
    signal_id: UUID
    rule_code: str
    signal_source: BeaconSignalSource
    evidence_digest: str
    action: BeaconLifecycleAction
    actor_membership_id: UUID
    action_at: datetime
    snooze_until: datetime | None
    created_at: datetime


class BeaconLifecycleProjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: BeaconLifecycleStatus
    latest_event: BeaconLifecycleEventResponse | None
    temporarily_suppressed: bool


class BeaconSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condition_key: UUID
    evidence_digest: str
    definition_id: str
    definition_version: int
    rule_code: str
    source: BeaconSignalSource
    title: str
    category: BeaconCategory
    severity: BeaconSeverity
    priority: BeaconPriorityResponse
    lifecycle: BeaconLifecycleProjectionResponse
    confidence: BeaconConfidenceResponse
    supporting_facts: tuple[BeaconSupportingFactResponse, ...]
    recommended_action: str
    created_at: datetime
    expires_at: datetime
    expiration_policy: BeaconExpirationPolicy


class BeaconSignalPage(BaseModel):
    items: tuple[BeaconSignalResponse, ...]
    snoozed_items: tuple[BeaconSignalResponse, ...]
    evaluated_at: datetime
    expires_at: datetime
    lifecycle_commands_available: bool


class BeaconLifecycleCommandRequest(BaseModel):
    evidence_digest: str = Field(min_length=64, max_length=64)


class BeaconSnoozeCommandRequest(BeaconLifecycleCommandRequest):
    snooze_until: datetime


class BeaconLifecycleHistoryResponse(BaseModel):
    items: tuple[BeaconLifecycleEventResponse, ...]
