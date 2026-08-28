from datetime import date, datetime
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
