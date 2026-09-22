from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class LeadStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    APPOINTMENT_NEEDED = "appointment_needed"
    SCHEDULED = "scheduled"
    ESTIMATE_FOLLOW_UP = "estimate_follow_up"
    WON = "won"
    LOST = "lost"
    NURTURE = "nurture"


class LeadCreate(Schema):
    branch_id: UUID
    customer_id: UUID | None = None
    prospect_name: str | None = Field(default=None, max_length=300)
    contact_phone: str | None = Field(default=None, max_length=40)
    contact_email: str | None = Field(default=None, max_length=320)
    lead_source: str = Field(min_length=1, max_length=80)
    source_detail: str | None = Field(default=None, max_length=300)
    source_system: str | None = Field(default=None, max_length=80)
    source_provider_id: str | None = Field(default=None, max_length=200)
    source_version: str | None = Field(default=None, max_length=80)
    source_observed_at: datetime | None = None
    service_category: str | None = Field(default=None, max_length=120)
    service_need: str = Field(min_length=1, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)
    assigned_user_id: UUID | None = None
    next_action_type: str | None = Field(default=None, max_length=80)
    next_action_due_at: datetime | None = None

    @model_validator(mode="after")
    def subject_exists(self) -> LeadCreate:
        if self.customer_id is None and not (self.prospect_name or "").strip():
            raise ValueError("Customer or prospect name is required")
        if self.source_provider_id and not self.source_system:
            raise ValueError("Source system is required with a provider identity")
        return self


class LeadTransition(Schema):
    stage: LeadStage
    version: int = Field(ge=1)
    next_action_type: str | None = Field(default=None, max_length=80)
    next_action_due_at: datetime | None = None
    assigned_user_id: UUID | None = None
    appointment_id: UUID | None = None
    job_id: UUID | None = None
    estimate_id: UUID | None = None
    lost_reason: str | None = Field(default=None, max_length=200)
    attributable_value_minor: int | None = Field(default=None, ge=0)
    value_currency: str | None = Field(default=None, min_length=3, max_length=3)
    value_authority: str | None = Field(default=None, max_length=100)


class ContactActivityCreate(Schema):
    channel: str = Field(min_length=1, max_length=40)
    disposition: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=200)
    next_action_type: str | None = Field(default=None, max_length=80)
    next_action_due_at: datetime | None = None


class LeadResponse(Schema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID | None
    prospect_name: str | None
    contact_phone: str | None
    contact_email: str | None
    lead_source: str
    source_detail: str | None
    source_system: str | None
    source_provider_id: str | None
    source_version: str | None
    source_observed_at: datetime | None
    service_category: str | None
    service_need: str
    assigned_user_id: UUID | None
    stage: LeadStage
    created_at: datetime
    first_contact_at: datetime | None
    last_action_at: datetime | None
    next_action_type: str | None
    next_action_due_at: datetime | None
    contact_attempt_count: int
    appointment_id: UUID | None
    job_id: UUID | None
    estimate_id: UUID | None
    outcome: str | None
    lost_reason: str | None
    attributable_value_minor: int | None
    value_currency: str | None
    value_authority: str | None
    version: int
    attention_state: str | None = None


class LeadList(Schema):
    items: tuple[LeadResponse, ...]
    total: int
    filters: dict[str, str | None]


class PipelineBucket(Schema):
    key: str
    label: str
    count: int
    value_minor: int | None
    currency: str | None
    value_complete: bool
    drilldown_path: str


class PipelineProjection(Schema):
    as_of: datetime
    company_id: UUID
    branch_ids: tuple[UUID, ...]
    moving_forward: PipelineBucket
    needs_attention: PipelineBucket


class LeadHistoryResponse(Schema):
    id: UUID
    action_type: str
    from_stage: str | None
    to_stage: str | None
    detail: str | None
    actor_user_id: UUID
    occurred_at: datetime
