from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .readiness import ReadinessState
from .types import (
    CommunicationChannel,
    CommunicationDeliveryState,
    CommunicationPurpose,
    CommunicationType,
)


class CommunicationCreate(BaseModel):
    communication_type: CommunicationType
    channel: CommunicationChannel
    customer_id: UUID
    contact_id: UUID
    branch_id: UUID
    source_event_id: UUID
    request_key: str = Field(min_length=1, max_length=100)
    scheduled_at: AwareDatetime


class CommunicationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    communication_type: CommunicationType
    channel: CommunicationChannel
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    contact_id: UUID
    recipient_display: str
    source_event_id: UUID
    source_event_type: str
    source_entity_type: str
    source_entity_id: UUID | None
    request_identity: str
    state: CommunicationDeliveryState
    retry_count: int
    terminal_failure: bool
    scheduled_at: datetime
    sent_at: datetime | None
    failed_at: datetime | None
    error_code: str | None
    error_category: str | None
    created_at: datetime


class CommunicationPage(BaseModel):
    items: tuple[CommunicationItem, ...]


class MessageCatalogItem(BaseModel):
    message_class: CommunicationType
    owner_domain: str
    allowed_channels: tuple[CommunicationChannel, ...]
    template_version: str
    purpose: CommunicationPurpose
    policy_required: bool


class CommunicationsReadinessItem(BaseModel):
    email: ReadinessState
    sms: ReadinessState
    webhook: ReadinessState
    overall: ReadinessState
    synthetic_only: bool
    catalog_fingerprint: str


class CommunicationOperationsSummary(BaseModel):
    pending: int
    accepted_pending_delivery: int
    delivered: int
    needs_attention: int
    suppressed: int
    oldest_pending_at: datetime | None
