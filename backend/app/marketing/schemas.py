from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import AttributionResolution, AttributionRole, AttributionTargetType


class MarketingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ChannelResponse(MarketingSchema):
    id: UUID
    code: str
    name: str
    active: bool


class SourceResponse(MarketingSchema):
    id: UUID
    channel_id: UUID
    code: str
    name: str
    provider_family: str | None
    active: bool


class CampaignResponse(MarketingSchema):
    id: UUID
    source_id: UUID
    name: str
    state: str


class CatalogResponse(MarketingSchema):
    channels: tuple[ChannelResponse, ...]
    sources: tuple[SourceResponse, ...]
    campaigns: tuple[CampaignResponse, ...]


class ManualAttributionConfirmation(MarketingSchema):
    target_type: AttributionTargetType
    target_id: UUID
    branch_id: UUID | None = None
    touch_id: UUID | None = None
    role: AttributionRole
    resolution: AttributionResolution
    supporting_evidence_reference: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=1000)
    supersedes_assignment_id: UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def resolved_requires_touch(self) -> "ManualAttributionConfirmation":
        if self.resolution is AttributionResolution.RESOLVED and self.touch_id is None:
            raise ValueError("resolved attribution requires supporting touch evidence")
        return self


class AttributionResponse(MarketingSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    touch_id: UUID | None
    role: str
    method: str
    resolution: str
    supporting_evidence_reference: str
    reason: str | None
    actor_user_id: UUID | None
    supersedes_assignment_id: UUID | None
    assigned_at: datetime
    target_type: AttributionTargetType
    target_id: UUID


class ResolutionQueueResponse(MarketingSchema):
    items: tuple[AttributionResponse, ...]


class EvidenceCoverageResponse(MarketingSchema):
    as_of: datetime
    total_assignments: int
    resolved: int
    unknown: int
    conflicting: int
    not_available: int
    coverage_percent: int
    availability: str
    missing_components: tuple[str, ...]
