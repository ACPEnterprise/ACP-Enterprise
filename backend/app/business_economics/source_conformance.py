from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class EvidenceConfidence(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class EconomicComponent(str, Enum):
    JOB_IDENTITY = "job_identity"
    SERVICE_LINE = "service_line"
    REVENUE = "revenue"
    SETTLEMENT = "settlement"
    DIRECT_LABOR = "direct_labor"
    DIRECT_MATERIAL = "direct_material"
    OVERHEAD = "overhead"


@dataclass(frozen=True, slots=True)
class EvidenceAssertion:
    """Immutable public assertion; never an instruction to read raw source data."""

    assertion_id: str
    source_system: str
    source_authority: str
    component: EconomicComponent
    semantic_key: str
    value_digest: str
    evidence_digest: str
    package_digest: str
    confidence: EvidenceConfidence
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.assertion_id or not self.semantic_key:
            raise ValueError("assertion and semantic identities are required")
        if not self.source_system or not self.source_authority:
            raise ValueError("source provenance is required")
        for digest in (self.value_digest, self.evidence_digest, self.package_digest):
            if not _SHA256.fullmatch(digest):
                raise ValueError("immutable SHA-256 provenance is required")
        if self.confidence is EvidenceConfidence.CONFLICTING:
            raise ValueError("conflict is assessed across assertions, not asserted")


@dataclass(frozen=True, slots=True)
class EconomicFinding:
    component: EconomicComponent
    confidence: EvidenceConfidence
    evidence_ids: tuple[str, ...]
    source_authorities: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    conflict_keys: tuple[str, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class SourceConformanceAssessment:
    findings: tuple[EconomicFinding, ...]
    assessment_sha256: str
    beacon_handoff_eligible: bool


_REQUIREMENTS: dict[EconomicComponent, tuple[str, ...]] = {
    EconomicComponent.JOB_IDENTITY: ("authoritative_job_identity",),
    EconomicComponent.SERVICE_LINE: ("authoritative_service_line",),
    EconomicComponent.REVENUE: (
        "source_reported_revenue",
        "finance_accepted_revenue_basis",
    ),
    EconomicComponent.SETTLEMENT: (
        "source_reported_payment_application",
        "control_reconciliation",
    ),
    EconomicComponent.DIRECT_LABOR: (
        "authoritative_job_time",
        "approved_labor_burden",
    ),
    EconomicComponent.DIRECT_MATERIAL: (
        "authoritative_job_material_consumption",
        "approved_cost_layer",
    ),
    EconomicComponent.OVERHEAD: (
        "finance_approved_overhead_pool",
        "versioned_allocation_policy",
    ),
}


def assess_source_conformance(
    assertions: tuple[EvidenceAssertion, ...],
) -> SourceConformanceAssessment:
    ordered = tuple(
        sorted(
            assertions,
            key=lambda item: (
                item.component.value,
                item.semantic_key,
                item.assertion_id,
            ),
        )
    )
    if len({item.assertion_id for item in ordered}) != len(ordered):
        raise ValueError("assertion identities must be unique")

    findings = tuple(_finding(component, ordered) for component in EconomicComponent)
    canonical = [
        {
            "component": item.component.value,
            "confidence": item.confidence.value,
            "evidence_ids": item.evidence_ids,
            "source_authorities": item.source_authorities,
            "missing_requirements": item.missing_requirements,
            "conflict_keys": item.conflict_keys,
        }
        for item in findings
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SourceConformanceAssessment(
        findings=findings,
        assessment_sha256=digest,
        beacon_handoff_eligible=any(
            item.confidence is EvidenceConfidence.CONFLICTING for item in findings
        ),
    )


def _finding(
    component: EconomicComponent, assertions: tuple[EvidenceAssertion, ...]
) -> EconomicFinding:
    selected = tuple(item for item in assertions if item.component is component)
    conflict_keys = tuple(
        sorted(
            key
            for key in {item.semantic_key for item in selected}
            if len({item.value_digest for item in selected if item.semantic_key == key})
            > 1
        )
    )
    if conflict_keys:
        confidence = EvidenceConfidence.CONFLICTING
        explanation = "Source assertions disagree; Business Economics preserves every assertion and selects no winner."
    elif not selected:
        confidence = EvidenceConfidence.UNKNOWN
        explanation = (
            "Required source evidence is absent; missing evidence is not zero."
        )
    elif any(item.confidence is EvidenceConfidence.UNKNOWN for item in selected):
        confidence = EvidenceConfidence.UNKNOWN
        explanation = "A source explicitly reports incomplete evidence; no economic amount is inferred."
    elif any(item.confidence is EvidenceConfidence.PARTIAL for item in selected):
        confidence = EvidenceConfidence.PARTIAL
        explanation = "Source evidence exists with explicit limitations and is not complete measurement."
    else:
        confidence = EvidenceConfidence.AVAILABLE
        explanation = "Conforming source evidence is available; accounting acceptance remains separately governed."

    supplied = {
        limit.removeprefix("satisfies:")
        for item in selected
        for limit in item.limitations
        if limit.startswith("satisfies:")
    }
    missing = tuple(
        requirement
        for requirement in _REQUIREMENTS[component]
        if requirement not in supplied
    )
    if missing and confidence is EvidenceConfidence.AVAILABLE:
        confidence = EvidenceConfidence.PARTIAL
        explanation = "Evidence is present but required provenance or policy inputs remain incomplete."
    return EconomicFinding(
        component=component,
        confidence=confidence,
        evidence_ids=tuple(item.assertion_id for item in selected),
        source_authorities=tuple(sorted({item.source_authority for item in selected})),
        missing_requirements=missing,
        conflict_keys=conflict_keys,
        explanation=explanation,
    )
