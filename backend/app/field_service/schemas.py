from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FieldSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ItineraryItem(FieldSchema):
    appointment_id: UUID
    appointment_number: str
    job_id: UUID | None
    job_number: str | None
    job_status: str | None
    job_version: int | None
    customer_display_name: str
    service_location_label: str
    window_start_at: datetime
    window_end_at: datetime
    assignment_status: str
    assignment_version: int
    arrival_state: str
    field_execution_enabled: bool = True


class Itinerary(FieldSchema):
    service_date: date
    technician_display_name: str
    items: tuple[ItineraryItem, ...]


class NoteInput(FieldSchema):
    note_type: Literal["work_performed", "internal", "customer_visible"] = (
        "work_performed"
    )
    content: str = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    expected_job_version: int = Field(ge=1)
    expected_assignment_version: int = Field(ge=1)


class ApprovalInput(FieldSchema):
    disposition: Literal["approved", "unavailable", "refused"]
    customer_name: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    expected_job_version: int = Field(ge=1)
    expected_assignment_version: int = Field(ge=1)


class HandoffInput(FieldSchema):
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    expected_job_version: int = Field(ge=1)
    expected_assignment_version: int = Field(ge=1)


class NonBillableInput(FieldSchema):
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    expected_job_version: int = Field(ge=1)
    expected_assignment_version: int = Field(ge=1)


class FieldJobState(FieldSchema):
    job_id: UUID
    assignment_id: UUID
    work_summary_recorded: bool
    customer_disposition: str | None
    completion_ready: bool
    requirement_snapshot_version: int | None
    missing_requirements: tuple[str, ...]
    commercial_authorization: Literal["accepted_estimate", "non_billable", "missing"]
    non_billable_reason: str | None
    invoice_handoff_status: str | None
    invoice_id: UUID | None


class FieldContact(FieldSchema):
    contact_id: UUID
    display_name: str
    phone: str | None
    email: str | None
    can_approve_work: bool


class FieldPriceBookItem(FieldSchema):
    item_id: UUID
    code: str
    name: str
    customer_description: str
    price_version_id: UUID
    unit_price: Decimal
    currency: str


class FieldInvoice(FieldSchema):
    invoice_id: UUID
    invoice_number: str
    status: str
    version: int
    open_amount: Decimal
    currency: str


class FieldPaymentState(FieldSchema):
    state: str
    invoice_id: UUID | None
    open_amount: Decimal | None
    currency: str | None
    receipt_status: str | None


class FieldCommunicationState(FieldSchema):
    communication_id: UUID
    message_class: str
    channel: str
    state: str
    created_at: datetime


class FieldJobSources(FieldSchema):
    job_id: UUID
    assignment_id: UUID
    assignment_version: int
    customer_id: UUID
    service_location_id: UUID
    contact: FieldContact | None
    invoice: FieldInvoice | None
    payment: FieldPaymentState
    communications: tuple[FieldCommunicationState, ...]
    completion: FieldJobState


class FieldArtifactIntentInput(FieldSchema):
    artifact_class: Literal["photo", "field_document", "equipment_evidence"]
    media_type: Literal["image/jpeg", "image/png", "image/heic", "application/pdf"]
    expected_size: int = Field(gt=0, le=25_000_000)
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_assignment_version: int = Field(ge=1)


class FieldArtifactIntentOut(FieldSchema):
    intent_id: UUID
    job_id: UUID
    upload_reference: str
    expires_at: datetime
    provider_state: Literal["synthetic_ready", "provider_required"]


class FieldArtifactFinalizeInput(FieldSchema):
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(gt=0, le=25_000_000)
    media_type: Literal["image/jpeg", "image/png", "image/heic", "application/pdf"]
    opaque_storage_reference: str = Field(min_length=8, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")


class FieldArtifactOut(FieldSchema):
    artifact_id: UUID
    job_id: UUID
    artifact_class: str
    media_type: str
    size: int
    content_digest: str
    created_at: datetime


class FieldEvidenceSummary(FieldSchema):
    kind: str
    state: str
    occurred_at: datetime
    protected_document_available: bool = False


class FieldEquipmentItem(FieldSchema):
    asset_id: UUID
    display_name: str
    lifecycle: str
    manufacturer: str | None = None
    model: str | None = None
    installation_state: str | None = None
    warranty_state: str | None = None
    service_history: tuple[FieldEvidenceSummary, ...] = ()
    evidence: tuple[FieldEvidenceSummary, ...] = ()


class FieldEquipmentProjection(FieldSchema):
    job_id: UUID
    items: tuple[FieldEquipmentItem, ...]
    history_limit: int
    attachment_upload_state: Literal["source_required"] = "source_required"


class FieldEstimateLine(FieldSchema):
    position: int
    title: str
    description: str | None
    quantity: Decimal
    line_total: Decimal
    currency: str


class FieldEstimatePresentation(FieldSchema):
    job_id: UUID
    available: bool
    estimate_number: str | None = None
    estimate_status: str | None = None
    acceptance_status: str | None = None
    revision_number: int | None = None
    revision_status: str | None = None
    proposal_title: str | None = None
    customer_message: str | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    expires_at: datetime | None = None
    lines: tuple[FieldEstimateLine, ...] = ()
    customer_handoff_state: Literal["server_authority_required"] = (
        "server_authority_required"
    )


class FieldHistoryItem(FieldSchema):
    job_id: UUID
    job_number: str
    completed_at: datetime
    customer_display_name: str
    service_location_label: str


class FieldHistoryProjection(FieldSchema):
    days: int
    limit: int
    items: tuple[FieldHistoryItem, ...]


class FieldFleetItem(FieldSchema):
    asset_id: UUID
    display_name: str
    lifecycle: str
    readiness_state: str | None = None
    inspection_state: str | None = None
    maintenance_state: str | None = None
    out_of_service: bool = False
    custody_state: str | None = None


class FieldReadinessProjection(FieldSchema):
    fleet: tuple[FieldFleetItem, ...]
    workforce_profile_available: bool
    branch_eligible: bool
    availability_state: str | None
    inspection_interaction: Literal["policy_required", "source_required"]
    notification_inbox: Literal["source_required"] = "source_required"
    push_provider: Literal["external_provider_required"] = "external_provider_required"
    payment_collection: Literal["not_authorized"] = "not_authorized"
