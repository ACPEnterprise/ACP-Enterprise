from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class WorkforceEligibilityQuery:
    company_id: UUID
    authorized_branch_ids: frozenset[UUID]
    branch_id: UUID
    window_start_at: datetime
    window_end_at: datetime
    required_capability_codes: frozenset[str] = frozenset()
    required_language_codes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EligibleTechnician:
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
