from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkforceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkforceCapabilityItem(WorkforceSchema):
    code: str
    display_name: str
    proficiency: str
    status: str


class WorkforceCertificationItem(WorkforceSchema):
    code: str
    display_name: str
    credential_reference: str
    status: str
    issued_on: date | None
    expires_on: date | None


class WorkforceLanguageItem(WorkforceSchema):
    code: str
    english_name: str
    native_name: str | None
    spoken_proficiency: str
    customer_facing_eligible: bool
    interpreter_verified: bool
    status: str


class WorkforceBranchItem(WorkforceSchema):
    branch_id: UUID
    status: str
    starts_on: date | None
    ends_on: date | None


class WorkforceAvailabilityItem(WorkforceSchema):
    branch_id: UUID
    start_at: datetime
    end_at: datetime
    status: str
    source: str


class WorkforceEmployeeSummary(WorkforceSchema):
    employee_id: UUID
    employee_number: str
    display_name: str
    job_title: str | None
    employee_type: str
    employee_status: str
    home_branch_id: UUID | None
    profile_id: UUID | None
    profile_status: str | None
    technician: bool
    capability_codes: tuple[str, ...]
    language_codes: tuple[str, ...]
    readiness_state: Literal["READY", "BLOCKED", "INSUFFICIENT_EVIDENCE"]
    readiness_blockers: tuple[str, ...]
    updated_at: datetime


class WorkforceEmployeeDetail(WorkforceEmployeeSummary):
    capabilities: tuple[WorkforceCapabilityItem, ...]
    certifications: tuple[WorkforceCertificationItem, ...]
    languages: tuple[WorkforceLanguageItem, ...]
    branches: tuple[WorkforceBranchItem, ...]
    work_restrictions: tuple[str, ...]
    equipment_capabilities: tuple[WorkforceCapabilityItem, ...]
    availability: tuple[WorkforceAvailabilityItem, ...]


class WorkforceDirectory(WorkforceSchema):
    items: tuple[WorkforceEmployeeSummary, ...]
    total: int


class WorkforceEligibilityRequest(WorkforceSchema):
    branch_id: UUID
    window_start_at: datetime
    window_end_at: datetime
    required_capability_codes: frozenset[str] = frozenset()
    required_language_codes: frozenset[str] = frozenset()


class WorkforceEligibilityItem(WorkforceSchema):
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


class WorkforceEligibilityResponse(WorkforceSchema):
    items: tuple[WorkforceEligibilityItem, ...]
