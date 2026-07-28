from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidenceLevel,
    BeaconExpirationPolicy,
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


class BeaconSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_code: str
    source: BeaconSignalSource
    title: str
    category: BeaconCategory
    severity: BeaconSeverity
    priority: BeaconPriorityResponse
    confidence: BeaconConfidenceResponse
    supporting_facts: tuple[BeaconSupportingFactResponse, ...]
    recommended_action: str
    created_at: datetime
    expires_at: datetime
    expiration_policy: BeaconExpirationPolicy


class BeaconSignalPage(BaseModel):
    items: tuple[BeaconSignalResponse, ...]
    evaluated_at: datetime
    expires_at: datetime
