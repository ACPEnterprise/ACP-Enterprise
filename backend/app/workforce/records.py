from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True)
class WorkforceCapabilityRecord:
    capability_id: UUID
    code: str
    display_name: str
    proficiency: str
    status: str


@dataclass(frozen=True)
class WorkforceCertificationRecord:
    certification_id: UUID
    code: str
    display_name: str
    credential_reference: str
    status: str
    issued_on: date | None
    expires_on: date | None


@dataclass(frozen=True)
class WorkforceLanguageRecord:
    language_id: UUID
    code: str
    english_name: str
    native_name: str | None
    spoken_proficiency: str
    reading_proficiency: str | None
    writing_proficiency: str | None
    customer_facing_eligible: bool
    interpreter_verified: bool
    status: str


@dataclass(frozen=True)
class WorkforceEquipmentRecord:
    equipment_capability_id: UUID
    code: str
    display_name: str
    proficiency: str
    status: str


@dataclass(frozen=True)
class WorkforceBranchEligibilityRecord:
    branch_id: UUID
    status: str
    starts_on: date | None
    ends_on: date | None


@dataclass(frozen=True)
class WorkforceGeographicCoverageRecord:
    coverage_type: str
    coverage_code: str
    status: str


@dataclass(frozen=True)
class WorkforceWorkRestrictionRecord:
    restriction_id: UUID
    code: str
    display_name: str
    status: str
    starts_on: date | None
    ends_on: date | None
    operational_note: str | None


@dataclass(frozen=True)
class WorkforceCapabilityProfileRecord:
    id: UUID
    company_id: UUID
    employee_id: UUID
    status: str
    concurrency_version: int
    created_at: datetime
    updated_at: datetime
    capabilities: tuple[WorkforceCapabilityRecord, ...] = ()
    certifications: tuple[WorkforceCertificationRecord, ...] = ()
    equipment_capabilities: tuple[WorkforceEquipmentRecord, ...] = ()
    branch_eligibilities: tuple[WorkforceBranchEligibilityRecord, ...] = ()
    geographic_coverages: tuple[WorkforceGeographicCoverageRecord, ...] = ()
    work_restrictions: tuple[WorkforceWorkRestrictionRecord, ...] = ()
    languages: tuple[WorkforceLanguageRecord, ...] = ()
