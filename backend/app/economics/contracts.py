from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.economics.domain import Confidence, EconomicCategory, EvidenceKind


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    kind: EvidenceKind
    reference_id: str
    source_system: str
    source_record_type: str
    source_version: str
    content_digest: str
    observed_at: datetime
    explanation: str
    business_event_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RecordBusinessFact:
    branch_id: UUID | None
    subject_type: str
    subject_id: UUID
    category: EconomicCategory
    fact_key: str
    amount_minor: int | None
    currency: str
    confidence: Confidence
    evidence: tuple[EvidenceInput, ...]
    occurred_at: datetime
    period_start: date
    period_end: date
    measurement_method: str
    accounting_basis: str = "accrual"
    correction_kind: str = "original"
    corrects_fact_id: UUID | None = None
    effective_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DefineAllocationPolicy:
    policy_key: str
    strategy: str
    driver_fact_key: str
    rationale: str
