from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.scheduling.types import AppointmentStatus


MAX_CALENDAR_RANGE = timedelta(days=93)


class AppointmentOrdering(StrEnum):
    CALENDAR_ASC = "calendar_asc"


@dataclass(frozen=True)
class AppointmentQuery:
    """Immutable query intent; contains no persistence implementation."""

    company_id: UUID
    authorized_branch_ids: frozenset[UUID]
    appointment_id: UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    branch_id: UUID | None = None
    statuses: frozenset[AppointmentStatus] = frozenset()
    customer_id: UUID | None = None
    service_location_id: UUID | None = None
    page: int = 1
    page_size: int = 100
    ordering: AppointmentOrdering = AppointmentOrdering.CALENDAR_ASC


@dataclass(frozen=True)
class AppointmentQueryRecord:
    id: UUID
    appointment_number: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: AppointmentStatus
    arrival_window_start_at: datetime | None
    arrival_window_end_at: datetime | None
    expected_duration_minutes: int | None
    capacity_units: Decimal | None
    concurrency_version: int
    reschedule_count: int
    rescheduled_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AppointmentQueryResult:
    items: tuple[AppointmentQueryRecord, ...]
    total_count: int
    page: int
    page_size: int
