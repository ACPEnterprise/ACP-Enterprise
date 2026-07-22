from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.jobs.types import JobCancellationReason, JobPauseReason, JobPriority, JobStatus
from app.scheduling.types import AppointmentStatus


@dataclass(frozen=True)
class JobCustomerSummary:
    id: UUID
    customer_number: str
    display_name: str


@dataclass(frozen=True)
class JobServiceLocationSummary:
    id: UUID
    nickname: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postal_code: str
    country: str


@dataclass(frozen=True)
class JobAppointmentSummary:
    appointment_id: UUID
    visit_sequence: int
    appointment_number: str
    status: AppointmentStatus
    arrival_window_start_at: datetime | None
    arrival_window_end_at: datetime | None
    expected_duration_minutes: int | None


@dataclass(frozen=True)
class JobDetail:
    id: UUID
    job_number: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: JobStatus
    concurrency_version: int
    activated_at: datetime | None
    started_at: datetime | None
    paused_at: datetime | None
    pause_reason_code: JobPauseReason | None
    completed_at: datetime | None
    completed_by_user_id: UUID | None
    cancelled_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancellation_reason_code: JobCancellationReason | None
    created_at: datetime
    created_by_user_id: UUID | None
    updated_at: datetime
    updated_by_user_id: UUID | None
    job_type_code: str | None
    priority: JobPriority
    customer_reported_problem: str | None
    internal_description: str | None
    customer: JobCustomerSummary
    service_location: JobServiceLocationSummary
    appointments: tuple[JobAppointmentSummary, ...]


@dataclass(frozen=True)
class JobListItem:
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
    appointment_count: int
    earliest_appointment_start_at: datetime | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    concurrency_version: int


@dataclass(frozen=True)
class PaginatedJobs:
    items: tuple[JobListItem, ...]
    page: int
    page_size: int
    total_count: int
    total_pages: int
