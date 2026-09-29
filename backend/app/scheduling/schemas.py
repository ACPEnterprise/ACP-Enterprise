from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.scheduling.types import (
    AppointmentCancellationReason,
    AppointmentRescheduleReason,
    AppointmentStatus,
)


class SchedulingApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppointmentCreateRequest(SchedulingApiSchema):
    idempotency_key: UUID | None = Field(
        default=None,
        description="Stable retry identity for deterministic Appointment creation.",
    )
    branch_id: UUID = Field(description="Authorized Branch receiving the Appointment.")
    customer_id: UUID = Field(description="Customer receiving service.")
    service_location_id: UUID = Field(description="Customer Service Location.")
    arrival_window_start_at: AwareDatetime = Field(
        description="Timezone-aware start of the customer arrival window."
    )
    arrival_window_end_at: AwareDatetime = Field(
        description="Timezone-aware end of the customer arrival window."
    )
    expected_duration_minutes: int = Field(
        gt=0, description="Expected service duration in whole minutes."
    )
    capacity_units: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
        max_digits=10,
        decimal_places=2,
        description="Branch scheduling capacity required by the Appointment.",
    )


class AppointmentCancellationRequest(SchedulingApiSchema):
    expected_version: int = Field(
        ge=1, description="Appointment concurrency version observed by the caller."
    )
    reason_code: AppointmentCancellationReason = Field(
        description="Controlled reason for cancelling the Appointment."
    )


class AppointmentRescheduleRequest(SchedulingApiSchema):
    expected_version: int = Field(
        ge=1, description="Appointment concurrency version observed by the caller."
    )
    arrival_window_start_at: AwareDatetime = Field(
        description="Timezone-aware start of the replacement arrival window."
    )
    arrival_window_end_at: AwareDatetime = Field(
        description="Timezone-aware end of the replacement arrival window."
    )
    expected_duration_minutes: int = Field(
        gt=0, description="Replacement expected service duration in whole minutes."
    )
    capacity_units: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
        description="Capacity required for the replacement working interval.",
    )
    reason_code: AppointmentRescheduleReason = Field(
        description="Controlled reason for rescheduling the Appointment."
    )


class AppointmentResponse(SchedulingApiSchema):
    id: UUID
    appointment_number: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: AppointmentStatus
    arrival_window_start_at: AwareDatetime | None
    arrival_window_end_at: AwareDatetime | None
    expected_duration_minutes: int | None
    capacity_units: Decimal | None
    concurrency_version: int = Field(ge=1)
    reschedule_count: int = Field(ge=0)
    rescheduled_at: AwareDatetime | None
    cancelled_at: AwareDatetime | None
    cancellation_reason_code: AppointmentCancellationReason | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AppointmentSummary(AppointmentResponse):
    """Stable calendar/list representation supplied by the Query Engine."""


class AppointmentDetail(AppointmentResponse):
    """Stable Appointment detail representation supplied by the Query Engine."""


class CalendarQueryResult(SchedulingApiSchema):
    items: tuple[AppointmentSummary, ...]
    total_count: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    start_at: AwareDatetime
    end_at: AwareDatetime


class BranchCalendarTechnician(SchedulingApiSchema):
    employee_id: UUID
    employee_number: str
    display_name: str
    job_title: str | None
    readiness: Literal["AVAILABLE", "UNAVAILABLE", "READINESS_BLOCKED"]
    readiness_reasons: tuple[str, ...]
    availability_confidence: str


class BranchCalendarRoster(SchedulingApiSchema):
    branch_id: UUID
    window_start_at: AwareDatetime
    window_end_at: AwareDatetime
    technicians: tuple[BranchCalendarTechnician, ...]


class BranchWeeklyIntervalInput(SchedulingApiSchema):
    day_of_week: int = Field(ge=0, le=6)
    start_minute: int = Field(ge=0, lt=1440)
    end_minute: int = Field(gt=0, le=1440)
    capacity_units: Decimal = Field(gt=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def valid_window(self):
        if self.end_minute <= self.start_minute:
            raise ValueError("Operating interval end must follow start.")
        return self


class BranchSchedulingExceptionInput(SchedulingApiSchema):
    exception_date: date
    start_minute: int | None = Field(default=None, ge=0, lt=1440)
    end_minute: int | None = Field(default=None, gt=0, le=1440)
    is_closed: bool
    capacity_units: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    reason_code: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def valid_exception(self):
        if (self.start_minute is None) != (self.end_minute is None):
            raise ValueError("Exception start and end must both be supplied.")
        if self.start_minute is not None and self.end_minute <= self.start_minute:
            raise ValueError("Exception end must follow start.")
        if self.is_closed and self.capacity_units is not None:
            raise ValueError("Closed exceptions cannot declare capacity.")
        if not self.is_closed and self.capacity_units is None:
            raise ValueError("Open exceptions require capacity.")
        return self


class BranchSchedulingPolicyWrite(SchedulingApiSchema):
    expected_version: int | None = Field(default=None, ge=1)
    timezone: str = Field(min_length=1, max_length=64)
    active: bool
    booking_horizon_days: int = Field(gt=0, le=1095)
    minimum_notice_minutes: int = Field(ge=0, le=10080)
    slot_interval_minutes: int = Field(gt=0, le=1440)
    default_capacity_units: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    weekly_intervals: tuple[BranchWeeklyIntervalInput, ...] = ()
    exceptions: tuple[BranchSchedulingExceptionInput, ...] = ()
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def valid_policy(self):
        ordered = sorted(
            self.weekly_intervals,
            key=lambda item: (item.day_of_week, item.start_minute),
        )
        for prior, current in pairwise(ordered):
            if (
                prior.day_of_week == current.day_of_week
                and prior.end_minute > current.start_minute
            ):
                raise ValueError("Weekly operating intervals cannot overlap.")
        if self.active and not self.weekly_intervals:
            raise ValueError("An active calendar requires operating hours.")
        return self


class BranchSchedulingPolicyResponse(SchedulingApiSchema):
    branch_id: UUID
    timezone: str
    status: Literal["NOT_CONFIGURED", "ACTIVE", "INACTIVE"]
    readiness: Literal["SCHEDULING_READY", "SCHEDULING_SETUP_REQUIRED"]
    blockers: tuple[str, ...]
    version: int | None
    booking_horizon_days: int | None
    minimum_notice_minutes: int | None
    slot_interval_minutes: int | None
    default_capacity_units: Decimal | None
    weekly_intervals: tuple[BranchWeeklyIntervalInput, ...]
    exceptions: tuple[BranchSchedulingExceptionInput, ...]
