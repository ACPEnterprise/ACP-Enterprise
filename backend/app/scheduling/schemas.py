from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.scheduling.types import (
    AppointmentCancellationReason,
    AppointmentRescheduleReason,
    AppointmentStatus,
)


class SchedulingApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppointmentCreateRequest(SchedulingApiSchema):
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
