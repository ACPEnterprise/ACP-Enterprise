from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidenceLevel,
    BeaconExpirationPolicy,
    BeaconSeverity,
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


class BeaconSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_code: str
    title: str
    category: BeaconCategory
    severity: BeaconSeverity
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
