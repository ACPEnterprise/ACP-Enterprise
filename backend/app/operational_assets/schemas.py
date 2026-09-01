from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AssetCreate(Schema):
    branch_id: UUID
    asset_number: str = Field(min_length=1, max_length=80)
    asset_class: str
    display_name: str = Field(min_length=1, max_length=200)
    predecessor_asset_id: UUID | None = None
    provenance: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=160)


class AssetOut(Schema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    asset_number: str
    asset_class: str
    display_name: str
    lifecycle: str
    predecessor_asset_id: UUID | None
    provenance: dict[str, object]
    identity_digest: str
    version: int
    created_at: datetime
    updated_at: datetime


class EvidenceCreate(Schema):
    evidence_type: str
    state: str
    value: dict[str, object] = Field(default_factory=dict)
    source_reference: str | None = Field(default=None, max_length=240)
    protected_document_id: UUID | None = None
    occurred_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=160)


class EvidenceOut(Schema):
    id: UUID
    asset_id: UUID
    evidence_type: str
    state: str
    value: dict[str, object]
    source_reference: str | None
    protected_document_id: UUID | None
    occurred_at: datetime
    evidence_digest: str
    created_at: datetime


class RelationshipCreate(Schema):
    relationship_type: str
    related_entity_id: UUID
    valid_from: datetime
    valid_to: datetime | None = None
    idempotency_key: str = Field(min_length=1, max_length=160)


class RelationshipOut(Schema):
    id: UUID
    asset_id: UUID
    relationship_type: str
    related_entity_id: UUID
    valid_from: datetime
    valid_to: datetime | None
    evidence_digest: str
    created_at: datetime


class LifecycleChange(Schema):
    lifecycle: str
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=160)


class AssetDetail(Schema):
    asset: AssetOut
    evidence: list[EvidenceOut]
    relationships: list[RelationshipOut]
    readiness: str
    readiness_reasons: list[str]


class AssetActionCreate(Schema):
    action_type: str
    state: str = Field(min_length=1, max_length=40)
    related_entity_id: UUID | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    occurred_at: datetime
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)


class AssetActionOut(Schema):
    id: UUID
    asset_id: UUID
    action_type: str
    state: str
    related_entity_id: UUID | None
    payload: dict[str, object]
    occurred_at: datetime
    asset_version: int
    evidence_digest: str
    created_at: datetime
