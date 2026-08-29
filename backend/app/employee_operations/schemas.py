from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmployeeOperationsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmployeeServiceLocation(EmployeeOperationsSchema):
    label: str
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postal_code: str
    country: str


class EmployeeDayAssignment(EmployeeOperationsSchema):
    appointment_id: UUID
    appointment_number: str
    appointment_status: str
    job_id: UUID | None
    job_number: str | None
    job_status: str | None
    service_category: str | None
    window_start_at: datetime
    window_end_at: datetime
    assignment_role: Literal["primary", "crew"]
    assignment_status: str
    designation: Literal["current", "next"] | None = None
    customer_display_name: str
    service_location: EmployeeServiceLocation


class EmployeeDayResponse(EmployeeOperationsSchema):
    business_date: date
    timezone: str
    assignments: tuple[EmployeeDayAssignment, ...]
