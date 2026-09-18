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


class RealRosterBindingRequest(WorkforceSchema):
    employee_id: UUID


class RealRosterReadinessItem(WorkforceSchema):
    roster_key: str
    display_name: str
    operating_role: str
    field_tech: bool
    employee_id: UUID | None
    employee_display_name: str | None
    employment_status: Literal["active", "inactive", "leave", "terminated"] | None
    user_state: str
    employee_state: str
    membership_state: str
    branch_state: str
    role_state: str
    workforce_profile_state: str
    technician_capability_state: str
    mobile_state: str
    credential_state: str
    availability_state: str
    dispatch_state: str
    timekeeping_state: str
    payroll_linkage_state: str
    identity_confirmed_at: datetime | None
    readiness_window_start_at: datetime | None
    readiness_window_end_at: datetime | None
    readiness_source: str | None
    blockers: tuple[str, ...]


class RealRosterSourceEvidence(WorkforceSchema):
    source_system: Literal["HCP"]
    source_employee_id: str
    source_disposition: str
    source_branch_id: UUID
    acp_employee_id: UUID | None
    roster_key: str | None
    certification_state: Literal[
        "ACP_EMPLOYEE_BOUND",
        "SOURCE_ONLY",
        "OWNER_CERTIFICATION_REQUIRED",
        "NOT_EMPLOYEE",
    ]
    evidence_version: int
    recorded_at: datetime


class RealRosterReadiness(WorkforceSchema):
    items: tuple[RealRosterReadinessItem, ...]
    source_evidence: tuple[RealRosterSourceEvidence, ...]
    total: int
    bound: int
    field_tech_total: int
    field_tech_capability_ready: int
    source_evidence_total: int
    source_only_total: int
    certification_required_total: int
    login_ready_total: int
    membership_ready_total: int
    branch_ready_total: int
    mobile_ready_total: int
    dispatch_ready_total: int
    timekeeping_ready_total: int
    payroll_identity_ready_total: int


class SourceCertificationDecisionRequest(WorkforceSchema):
    decision: Literal[
        "CONFIRM", "SELECT_EXISTING", "CREATE_ONBOARD", "HOLD", "LEGACY_ONLY"
    ]
    expected_revision: int = Field(ge=0)
    employee_id: UUID | None = None
    onboarding_request_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=500)


class SourceCertificationRevisionItem(WorkforceSchema):
    revision: int
    decision: str
    employee_id: UUID | None
    onboarding_request_id: UUID | None
    actor_user_id: UUID
    reason: str
    occurred_at: datetime


class SourceCertificationItem(WorkforceSchema):
    source_system: Literal["HCP"]
    source_employee_id: str
    source_disposition: str
    source_branch_id: UUID
    source_branch_name: str
    evidence_reference: str
    evidence_digest: str
    mechanically_supported_employee_id: UUID | None
    mechanically_supported_employee_name: str | None
    decision: str | None
    revision: int
    employee_id: UUID | None
    employee_name: str | None
    onboarding_request_id: UUID | None
    reason: str | None
    decided_at: datetime | None
    history: tuple[SourceCertificationRevisionItem, ...]


class SourceCertificationLedger(WorkforceSchema):
    items: tuple[SourceCertificationItem, ...]
    total: int
    undecided: int


class EmployeeAdministrationSummary(WorkforceEmployeeSummary):
    user_id: UUID | None
    membership_id: UUID | None
    membership_status: str | None
    user_status: str | None
    authorization_version: int | None
    branch_ids: tuple[UUID, ...]
    role_codes: tuple[str, ...]
    onboarding_status: str | None
    invitation_status: str | None
    delivery_status: str | None
    login_email: str | None
    masked_login: str | None
    access_status: Literal["ACTIVE", "DISABLED", "INVITED", "NOT_LINKED"]
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
    spoken_proficiency: str = Field(
        pattern="^(basic|conversational|professional|fluent|native)$"
    )
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


class FieldReadinessRequest(WorkforceSchema):
    branch_id: UUID
    window_start_at: datetime
    window_end_at: datetime
    reason: str = Field(min_length=3, max_length=240)


class FieldReadinessResponse(WorkforceSchema):
    profile_id: UUID
    capability_evidence_id: UUID
    availability_evidence_id: UUID


class EmployeeTimelineItem(WorkforceSchema):
    event_type: str
    occurred_at: datetime
    authority: Literal["ACP_NATIVE", "SOURCE_BACKED"]
    source: str
    actor_user_id: UUID | None
    actor_display_name: str | None
    description: str
    employee_id: UUID
    navigation_reference: str | None = None


class EmployeeTimeline(WorkforceSchema):
    employee_id: UUID
    items: tuple[EmployeeTimelineItem, ...]


class EmployeeNotificationTarget(WorkforceSchema):
    employee_id: UUID
    event_type: Literal[
        "NEW_ASSIGNMENT",
        "ASSIGNMENT_CHANGED",
        "JOB_CANCELED",
        "EMPLOYEE_ACTION_REQUIRED",
        "TIMEKEEPING_ISSUE",
    ]
    company_id: UUID
    branch_id: UUID
    membership_id: UUID | None
    user_id: UUID | None
    authorization_version: int | None
    state: Literal["READY", "BLOCKED"]
    blockers: tuple[str, ...]
    delivery_channel: Literal["EMPLOYEE_INBOX"] = "EMPLOYEE_INBOX"
    external_push_state: Literal["PROVIDER_REQUIRED"] = "PROVIDER_REQUIRED"
