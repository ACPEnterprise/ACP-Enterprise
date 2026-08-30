from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

LUMINARY_FINDING_VERSION = "luminary.finding.v1"
LUMINARY_BRIEFING_VERSION = "luminary.owner-briefing.v1"


class FindingClass(StrEnum):
    OBSERVED_FACT = "observed_fact"
    MEASURED_COMPARISON = "measured_comparison"
    SUPPORTED_ASSOCIATION = "supported_association"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    POLICY_REQUIRED = "policy_required"


class FindingType(StrEnum):
    BUSINESS_PERFORMANCE = "business_performance"
    PROFITABLE_JOB = "profitable_job"
    UNPROFITABLE_JOB = "unprofitable_job"
    PERIOD_CHANGE = "period_change"
    LABOR_COST_CHANGE = "labor_cost_change"
    MATERIAL_COST_CHANGE = "material_cost_change"
    BRANCH_COMPARISON = "branch_comparison"
    MISSING_EVIDENCE = "missing_evidence"
    ALLOCATION_POLICY = "allocation_policy"
    BEACON_ATTENTION = "beacon_attention"


class EvidenceQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    source_domain: str
    record_type: str
    record_id: str
    digest: str


@dataclass(frozen=True, slots=True)
class MeasuredObservation:
    metric: str
    value_minor: int | None
    currency: str | None
    unit: str
    comparison_value_minor: int | None = None
    change_minor: int | None = None


@dataclass(frozen=True, slots=True)
class LuminaryFinding:
    finding_id: UUID
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    finding_class: FindingClass
    finding_type: FindingType
    title: str
    summary: str
    observations: tuple[MeasuredObservation, ...]
    evidence: tuple[EvidenceReference, ...]
    evidence_package_digest: str
    confidence_percent: int
    completeness: EvidenceQuality
    freshness: str
    explanation: str
    limitations: tuple[str, ...]
    investigate_next: tuple[str, ...]
    engine_version: str
    definition_version: str
    finding_digest: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class BeaconConditionReference:
    signal_id: str
    condition_key: str
    definition_id: str
    severity: str
    lifecycle: str
    evidence_digest: str
    title: str


@dataclass(frozen=True, slots=True)
class LuminaryEvidencePackage:
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    economics: dict[str, object]
    economics_results: tuple[EvidenceReference, ...]
    beacon_conditions: tuple[BeaconConditionReference, ...]
    package_digest: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class OwnerBriefing:
    briefing_id: UUID
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    evidence_package_digest: str
    finding_ids: tuple[UUID, ...]
    finding_digests: tuple[str, ...]
    sections: tuple[tuple[str, tuple[UUID, ...]], ...]
    completeness: EvidenceQuality
    summary: str
    briefing_digest: str
    generated_at: datetime
