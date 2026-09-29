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


class GoogleAdsAccountBindingCreate(MarketingSchema):
    connection_binding_id: UUID
    branch_id: UUID
    external_customer_id: str = Field(pattern=r"^[0-9]{10}$")
    descriptive_name: str = Field(min_length=1, max_length=200)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    time_zone: str | None = Field(default=None, max_length=100)
    ingestion_enabled: bool = False
    reason: str = Field(min_length=3, max_length=300)


class GoogleAdsAccountBindingResponse(MarketingSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    provider_account_id: UUID
    connection_binding_id: UUID
    ingestion_enabled: bool
    bound_at: datetime


class GoogleAdsConnectionReadinessResponse(MarketingSchema):
    connection_status: str
    environment: str
    oauth_client_configured: bool
    callback_configured: bool
    developer_token_configured: bool
    environment_safe_secret_custody: bool
    live_ingestion_enabled: bool
    authorization_available: bool
    granted_scopes: tuple[str, ...]
    connected_at: datetime | None
    bound_account_count: int
    blockers: tuple[str, ...]


class GoogleAdsOAuthStartResponse(MarketingSchema):
    authorization_url: str


class GoogleAdsAccountBindingSummary(MarketingSchema):
    id: UUID
    branch_id: UUID
    provider_account_id: UUID
    external_customer_id: str
    descriptive_name: str
    currency_code: str | None
    time_zone: str | None
    ingestion_enabled: bool
    bound_at: datetime


class ProviderSyncStatusResponse(MarketingSchema):
    provider_account_id: UUID
    status: str
    requested_start_at: datetime | None
    requested_end_at: datetime | None
    record_count: int
    exception_count: int
    completed_at: datetime | None


class ProviderCoverageResponse(MarketingSchema):
    provider_account_id: UUID
    interval_start: datetime
    interval_end: datetime
    as_of: datetime
    attribution_policy_version: str
    evidence_count: int
    coverage_percent: int
    missing_components: list[str]
    availability: str


class ReconciliationFindingResponse(MarketingSchema):
    id: UUID
    provider_account_id: UUID
    kind: str
    state: str
    missing_components: list[str]
    observed_at: datetime
