from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.jobs.types import (
    JobCancellationReason,
    JobPauseReason,
    JobPriority,
    JobReopeningReason,
    JobStatus,
)
from app.scheduling.types import AppointmentStatus


class JobsApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class JobCreateRequest(JobsApiSchema):
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    job_type_code: str | None = Field(default=None, max_length=64)
    priority: JobPriority = JobPriority.NORMAL
    customer_reported_problem: str | None = None
    internal_description: str | None = None


class JobCreateFromAppointmentRequest(JobsApiSchema):
    appointment_id: UUID
    job_type_code: str | None = Field(default=None, max_length=64)
    priority: JobPriority = JobPriority.NORMAL
    customer_reported_problem: str | None = None
    internal_description: str | None = None


class JobVersionRequest(JobsApiSchema):
    expected_version: int = Field(ge=1)


class JobPauseRequest(JobVersionRequest):
    reason_code: JobPauseReason


class JobCancelRequest(JobVersionRequest):
    reason_code: JobCancellationReason


class JobReopenRequest(JobVersionRequest):
    reason_code: JobReopeningReason


class JobMutationResponse(JobsApiSchema):
    id: UUID
    job_number: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: JobStatus
    job_type_code: str | None
    priority: JobPriority
    customer_reported_problem: str | None
    internal_description: str | None
    concurrency_version: int = Field(ge=1)
    activated_at: AwareDatetime | None
    started_at: AwareDatetime | None
    paused_at: AwareDatetime | None
    pause_reason_code: JobPauseReason | None
    completed_at: AwareDatetime | None
    completed_by_user_id: UUID | None
    cancelled_at: AwareDatetime | None
    cancelled_by_user_id: UUID | None
    cancellation_reason_code: JobCancellationReason | None
    created_at: AwareDatetime
    created_by_user_id: UUID | None
    updated_at: AwareDatetime
    updated_by_user_id: UUID | None


class JobCustomerResponse(JobsApiSchema):
    id: UUID
    customer_number: str
    display_name: str


class JobServiceLocationResponse(JobsApiSchema):
    id: UUID
    nickname: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postal_code: str
    country: str


class JobAppointmentResponse(JobsApiSchema):
    appointment_id: UUID
    visit_sequence: int = Field(ge=1)
    appointment_number: str
    status: AppointmentStatus
    arrival_window_start_at: AwareDatetime | None
    arrival_window_end_at: AwareDatetime | None
    expected_duration_minutes: int | None


class JobDetailResponse(JobMutationResponse):
    customer: JobCustomerResponse
    service_location: JobServiceLocationResponse
    appointments: tuple[JobAppointmentResponse, ...]


class JobListItemResponse(JobsApiSchema):
    id: UUID
    job_number: str
    branch_id: UUID
    customer_id: UUID
    customer_display_name: str
    service_location_id: UUID
    service_location_label: str
    status: JobStatus
    priority: JobPriority
    job_type_code: str | None
    customer_reported_problem_summary: str | None
    appointment_count: int = Field(ge=0)
    earliest_appointment_start_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    concurrency_version: int = Field(ge=1)


class PaginatedJobsResponse(JobsApiSchema):
    items: tuple[JobListItemResponse, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)
