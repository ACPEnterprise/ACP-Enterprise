from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DispatchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class TechnicianEligibilityItem(DispatchSchema):
    employee_id: UUID
    employee_number: str
    display_name: str
    branch_id: UUID
    job_title: str | None
    capability_codes: tuple[str, ...]
    language_codes: tuple[str, ...]
    decision: str
    reasons: tuple[str, ...]
    availability_confidence: str
    eligible: bool


class CrewMemberItem(DispatchSchema):
    id: UUID
    employee_id: UUID
    display_name: str
    status: str
    added_at: datetime


class AssignmentItem(DispatchSchema):
    id: UUID
    appointment_id: UUID
    appointment_number: str
    job_id: UUID | None
    company_id: UUID
    branch_id: UUID
    primary_employee_id: UUID | None
    primary_employee_name: str | None
    status: str
    arrival_state: str
    active_exception_code: str | None
    assignment_reason: str
    window_start_at: datetime
    window_end_at: datetime
    effective_at: datetime
    released_at: datetime | None
    version: int
    crew_members: tuple[CrewMemberItem, ...] = ()


class DispatchBoardItem(DispatchSchema):
    appointment_id: UUID
    appointment_number: str
    job_id: UUID | None
    branch_id: UUID
    status: str
    window_start_at: datetime
    window_end_at: datetime
    assignment: AssignmentItem | None


class DispatchBoardPage(DispatchSchema):
    items: tuple[DispatchBoardItem, ...]
    total_count: int


class AssignPrimaryRequest(DispatchSchema):
    employee_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    expected_version: int | None = Field(default=None, ge=1)


class AssignmentReasonRequest(DispatchSchema):
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    expected_version: int = Field(ge=1)


class CrewMutationRequest(AssignmentReasonRequest):
    employee_id: UUID


class ReconcileRequest(AssignmentReasonRequest):
    resolution: str = Field(pattern=r"^(restore_assigned|release)$")


class DispatchExceptionRequest(AssignmentReasonRequest):
    exception_code: str = Field(
        pattern=(
            r"^(assignment_ambiguous|technician_unavailable|customer_unavailable|"
            r"safety_condition|weather|other)$"
        )
    )


class ArrivalStateRequest(DispatchSchema):
    state: str = Field(pattern=r"^(en_route|arrived)$")
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
