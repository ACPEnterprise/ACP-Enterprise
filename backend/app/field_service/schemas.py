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


class FieldAssetHistory(FieldSchema):
    evidence_id: UUID
    evidence_type: str
    state: str
    occurred_at: datetime


class FieldAsset(FieldSchema):
    asset_id: UUID
    display_name: str
    asset_class: str
    lifecycle: str
    manufacturer: str | None
    model: str | None
    warranty_readiness: str
    service_history: tuple[FieldAssetHistory, ...]


class FieldFleetAsset(FieldSchema):
    asset_id: UUID
    display_name: str
    lifecycle: str
    readiness: str


class FieldPriceBookItem(FieldSchema):
    item_id: UUID
    code: str
    name: str
    customer_description: str
    price_version_id: UUID
    unit_price: Decimal
    currency: str


class FieldEstimate(FieldSchema):
    estimate_id: UUID
    estimate_number: str
    status: str
    acceptance_status: str
    revision_id: UUID
    revision_number: int
    title: str
    total_amount: Decimal
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


class FieldCapabilityGate(FieldSchema):
    capability: str
    state: Literal[
        "READY",
        "POLICY_REQUIRED",
        "PROVIDER_REQUIRED",
        "SOURCE_REQUIRED",
    ]
    reason: str


class FieldReadiness(FieldSchema):
    capabilities: tuple[FieldCapabilityGate, ...]
    authorization_root: str
    mutation_recovery: str


class FieldJobSources(FieldSchema):
    job_id: UUID
    assignment_id: UUID
    assignment_version: int
    customer_id: UUID
    service_location_id: UUID
    contact: FieldContact | None
    equipment: tuple[FieldAsset, ...]
    fleet: tuple[FieldFleetAsset, ...]
    estimates: tuple[FieldEstimate, ...]
    invoice: FieldInvoice | None
    payment: FieldPaymentState
    communications: tuple[FieldCommunicationState, ...]
    completion: FieldJobState
    gates: tuple[FieldCapabilityGate, ...]


class CompletedFieldJob(FieldSchema):
    job_id: UUID
    job_number: str
    branch_id: UUID
    status: str
    completed_at: datetime | None


class CompletedFieldHistory(FieldSchema):
    items: tuple[CompletedFieldJob, ...]


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
