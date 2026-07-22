from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.jobs.types import JobPriority, JobStatus


class JobSortField(StrEnum):
    JOB_NUMBER = "job_number"
    PRIORITY = "priority"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    ACTIVATED_AT = "activated_at"
    STARTED_AT = "started_at"
    COMPLETED_AT = "completed_at"
    CANCELLED_AT = "cancelled_at"
    CUSTOMER_DISPLAY_NAME = "customer_display_name"
    EARLIEST_APPOINTMENT_START_AT = "earliest_appointment_start_at"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class JobDateRange:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class JobDetailQuery:
    job_id: UUID


@dataclass(frozen=True)
class JobSearchQuery:
    branch_id: UUID | None = None
    statuses: frozenset[JobStatus] = frozenset()
    priorities: frozenset[JobPriority] = frozenset()
    job_type_codes: frozenset[str] = frozenset()
    job_number: str | None = None
    customer_id: UUID | None = None
    service_location_id: UUID | None = None
    appointment_id: UUID | None = None
    created_range: JobDateRange | None = None
    updated_range: JobDateRange | None = None
    activated_range: JobDateRange | None = None
    started_range: JobDateRange | None = None
    completed_range: JobDateRange | None = None
    cancelled_range: JobDateRange | None = None
    has_appointment: bool | None = None
    has_historical_completion: bool | None = None
    has_historical_cancellation: bool | None = None
    search_text: str | None = None
    page: int = 1
    page_size: int = 50
    sort_field: JobSortField = JobSortField.UPDATED_AT
    sort_direction: SortDirection = SortDirection.DESC


@dataclass(frozen=True)
class JobQueryScope:
    company_id: UUID
    authorized_branch_ids: frozenset[UUID]
