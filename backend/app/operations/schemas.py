from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.dispatch.schemas import AssignmentItem
from app.jobs.schemas import JobMutationResponse
from app.jobs.types import JobPriority
from app.scheduling.schemas import AppointmentResponse


class OperationsApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServiceRequestCreate(OperationsApiSchema):
    request_id: UUID = Field(
        description="Caller-stable identity used to make intake retries deterministic."
    )
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    arrival_window_start_at: AwareDatetime
    arrival_window_end_at: AwareDatetime
    expected_duration_minutes: int = Field(gt=0)
    capacity_units: Decimal = Field(
        default=Decimal("1.00"), gt=0, max_digits=10, decimal_places=2
    )
    job_type_code: str | None = Field(default=None, max_length=64)
    priority: JobPriority = JobPriority.NORMAL
    customer_reported_problem: str | None = None
    internal_description: str | None = None


class ServiceRequestResponse(OperationsApiSchema):
    request_id: UUID
    appointment: AppointmentResponse
    job: JobMutationResponse


class ExistingJobScheduleCreate(OperationsApiSchema):
    request_id: UUID = Field(
        description="Caller-stable identity preventing duplicate Appointments."
    )
    expected_job_version: int = Field(ge=1)
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    arrival_window_start_at: AwareDatetime
    arrival_window_end_at: AwareDatetime
    expected_duration_minutes: int = Field(gt=0)
    capacity_units: Decimal = Field(
        default=Decimal("1.00"), gt=0, max_digits=10, decimal_places=2
    )
    reserve_capacity: bool = Field(
        default=True,
        description="Reserve Branch capacity; false for Needs Scheduling appointments.",
    )


class ExistingJobScheduleResponse(OperationsApiSchema):
    request_id: UUID
    appointment: AppointmentResponse
    job: JobMutationResponse


class CalendarPlacementCreate(OperationsApiSchema):
    request_id: UUID
    expected_appointment_version: int = Field(ge=1)
    expected_assignment_version: int | None = Field(default=None, ge=1)
    employee_id: UUID
    arrival_window_start_at: AwareDatetime
    arrival_window_end_at: AwareDatetime
    expected_duration_minutes: int = Field(gt=0)
    capacity_units: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)


class CalendarPlacementResponse(OperationsApiSchema):
    appointment: AppointmentResponse
    assignment: AssignmentItem
