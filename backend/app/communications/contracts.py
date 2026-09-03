from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .types import (
    CommunicationChannel,
    CommunicationDeliveryState,
    CommunicationPurpose,
    CommunicationType,
)


@dataclass(frozen=True)
class CommunicationRequest:
    communication_type: CommunicationType
    channel: CommunicationChannel
    customer_id: UUID
    contact_id: UUID
    branch_id: UUID
    source_event_id: UUID
    request_key: str
    scheduled_at: datetime


@dataclass(frozen=True)
class CommunicationEvidence:
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


@dataclass(frozen=True)
class CommunicationPolicy:
    communication_type: CommunicationType
    source_event_types: frozenset[str]
    template_identifier: str
    consent_required: bool = True
    owner_domain: str = "communications"
    allowed_channels: frozenset[CommunicationChannel] = frozenset(
        {CommunicationChannel.EMAIL}
    )
    purpose: CommunicationPurpose = CommunicationPurpose.TRANSACTIONAL
    policy_required: bool = False


@dataclass(frozen=True)
class CommunicationOperationalMeasurement:
    measurement_version: str
    company_id: UUID
    branch_id: UUID | None
    submitted: int
    accepted: int
    delivered: int
    failed: int
    bounced_or_invalid_recipient: int
    suppressed: int
    uncertain_submission: int
    retry: int
    recovered: int
    webhook_replay: int
    final_pending: int
    final_accepted_pending_delivery: int
    final_delivered: int
    final_failed: int
    final_suppressed: int
    final_uncertain: int
    measurement_fingerprint: str
