from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class EmployeeAdministrationSummary(WorkforceEmployeeSummary):
    membership_id: UUID | None
    membership_status: str | None
    user_status: str | None
    authorization_version: int | None
    branch_ids: tuple[UUID, ...]
    role_codes: tuple[str, ...]
    onboarding_status: str | None
    masked_login: str | None
    mobile_readiness: Literal["READY", "BLOCKED", "NOT_LINKED"]
    mobile_readiness_blockers: tuple[str, ...]


class EmployeePermissionExplanation(WorkforceSchema):
    code: str
    name: str
    business_area: str
    authority: Literal["ROLE_DERIVED", "OWN_DATA_ONLY", "DENIED"]
    role_codes: tuple[str, ...]
    branch_scoped: bool


class EmployeeAdministrationDetail(EmployeeAdministrationSummary):
    permissions: tuple[EmployeePermissionExplanation, ...]
    workforce: WorkforceEmployeeDetail


class WorkforceProfileResponse(WorkforceSchema):
    id: UUID
    employee_id: UUID
    status: str
    concurrency_version: int


class CapabilityEvidenceRequest(WorkforceSchema):
    capability_id: UUID
    proficiency: str = Field(pattern="^(awareness|assisted|qualified|advanced|expert)$")


class CertificationEvidenceRequest(WorkforceSchema):
    certification_id: UUID
    credential_reference: str = Field(min_length=1, max_length=160)
    status: str = Field(pattern="^(pending|active|suspended|expired|revoked)$")
    issued_on: date | None = None
    expires_on: date | None = None


class LanguageEvidenceRequest(WorkforceSchema):
    language_id: UUID
    spoken_proficiency: str = Field(pattern="^(basic|conversational|professional|fluent|native)$")
    customer_facing_eligible: bool = False


class AvailabilityEvidenceRequest(WorkforceSchema):
    branch_id: UUID
    start_at: datetime
    end_at: datetime
    status: str = Field(pattern="^(available|unavailable|cancelled)$")
    source: str = Field(default="workforce_admin", min_length=1, max_length=80)


class WorkforceEvidenceResponse(WorkforceSchema):
    id: UUID
    created: bool
