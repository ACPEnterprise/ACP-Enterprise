from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from .source_conformance import (
    EconomicComponent,
    EvidenceAssertion,
    EvidenceConfidence,
    assess_source_conformance,
)

FINDING_DEFINITION_VERSION = "eco.findings.v1"


class FindingType(str, Enum):
    JOB_ECONOMIC_READINESS = "job_economic_readiness"
    SERVICE_LINE_READINESS = "service_line_readiness"
    REVENUE_INCONSISTENCY = "revenue_inconsistency"
    SETTLEMENT_INCONSISTENCY = "settlement_inconsistency"
    MATERIAL_INCONSISTENCY = "material_procurement_inconsistency"
    LABOR_EVIDENCE_READINESS = "labor_evidence_readiness"
    OVERHEAD_READINESS = "overhead_readiness"
    POTENTIAL_MARGIN_LEAKAGE = "potential_margin_leakage"


class FindingState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    ABSENT = "absent"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


class SubjectKind(str, Enum):
    JOB = "job"
    SERVICE_LINE = "service_line"


@dataclass(frozen=True, slots=True)
class FindingSubject:
    """Explicit reconciliation subject supplied by an owning domain."""

    subject_id: str
    subject_kind: SubjectKind
    reconciliation_key: str
    required_components: tuple[EconomicComponent, ...]

    def __post_init__(self) -> None:
        if not self.subject_id or not self.reconciliation_key:
            raise ValueError(
                "explicit subject and reconciliation identity are required"
            )
        if not self.required_components:
            raise ValueError("at least one required economic component is required")


@dataclass(frozen=True, slots=True)
class FindingEvidence:
    assertion_id: str
    source_system: str
    source_authority: str
    confidence: EvidenceConfidence
    evidence_digest: str
    value_digest: str
    package_digest: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EconomicInconsistencyFinding:
    finding_id: str
    definition_version: str
    finding_type: FindingType
    subject_id: str
    reconciliation_key: str
    component: EconomicComponent
    state: FindingState
    confidence: EvidenceConfidence
    measured_condition: str
    evidence: tuple[FindingEvidence, ...]
    source_authorities: tuple[str, ...]
    limitations: tuple[str, ...]
    explanation_facts: tuple[str, ...]


_TYPE_BY_COMPONENT = {
    EconomicComponent.JOB_IDENTITY: FindingType.JOB_ECONOMIC_READINESS,
    EconomicComponent.SERVICE_LINE: FindingType.SERVICE_LINE_READINESS,
    EconomicComponent.REVENUE: FindingType.REVENUE_INCONSISTENCY,
    EconomicComponent.SETTLEMENT: FindingType.SETTLEMENT_INCONSISTENCY,
    EconomicComponent.DIRECT_MATERIAL: FindingType.MATERIAL_INCONSISTENCY,
    EconomicComponent.DIRECT_LABOR: FindingType.LABOR_EVIDENCE_READINESS,
    EconomicComponent.OVERHEAD: FindingType.OVERHEAD_READINESS,
}


def evaluate_economic_findings(
    *,
    subjects: tuple[FindingSubject, ...],
    assertions: tuple[EvidenceAssertion, ...],
) -> tuple[EconomicInconsistencyFinding, ...]:
    """Create deterministic findings without calculating money or source precedence."""

    if len({subject.subject_id for subject in subjects}) != len(subjects):
        raise ValueError("finding subject identities must be unique")
    findings: list[EconomicInconsistencyFinding] = []
    for subject in sorted(subjects, key=lambda item: item.subject_id):
        selected = tuple(
            item
            for item in assertions
            if item.semantic_key == subject.reconciliation_key
        )
        component_findings: list[EconomicInconsistencyFinding] = []
        for component in sorted(
            subject.required_components, key=lambda item: item.value
        ):
            component_evidence = tuple(
                sorted(
                    (item for item in selected if item.component is component),
                    key=lambda item: item.assertion_id,
                )
            )
            finding = _component_finding(subject, component, component_evidence)
            component_findings.append(finding)
            if finding.finding_type not in {
                FindingType.JOB_ECONOMIC_READINESS,
                FindingType.SERVICE_LINE_READINESS,
            }:
                findings.append(finding)
            if _potential_leakage(finding):
                findings.append(
                    _build_finding(
                        subject=subject,
                        component=component,
                        finding_type=FindingType.POTENTIAL_MARGIN_LEAKAGE,
                        state=finding.state,
                        confidence=finding.confidence,
                        measured_condition=(
                            "Economic analysis is exposed to potential margin leakage because "
                            f"{finding.measured_condition}"
                        ),
                        evidence=component_evidence,
                        limitations=(
                            *finding.limitations,
                            "no_dollar_loss_calculated",
                            "no_remediation_authority",
                        ),
                        explanation_facts=(
                            *finding.explanation_facts,
                            "Potential leakage is a measured evidence condition, not a profit-loss amount.",
                        ),
                    )
                )
        findings.append(_aggregate_readiness(subject, component_findings, selected))
    return tuple(
        sorted(
            findings,
            key=lambda item: (
                item.subject_id,
                item.finding_type.value,
                item.component.value,
            ),
        )
    )


def _aggregate_readiness(
    subject: FindingSubject,
    component_findings: list[EconomicInconsistencyFinding],
    evidence: tuple[EvidenceAssertion, ...],
) -> EconomicInconsistencyFinding:
    ranking = {
        FindingState.CONFLICTING: 4,
        FindingState.UNKNOWN: 3,
        FindingState.ABSENT: 2,
        FindingState.PARTIAL: 1,
        FindingState.READY: 0,
    }
    state = max((item.state for item in component_findings), key=ranking.__getitem__)
    confidence = {
        FindingState.READY: EvidenceConfidence.AVAILABLE,
        FindingState.PARTIAL: EvidenceConfidence.PARTIAL,
        FindingState.ABSENT: EvidenceConfidence.UNKNOWN,
        FindingState.UNKNOWN: EvidenceConfidence.UNKNOWN,
        FindingState.CONFLICTING: EvidenceConfidence.CONFLICTING,
    }[state]
    return _build_finding(
        subject=subject,
        component=(
            EconomicComponent.JOB_IDENTITY
            if subject.subject_kind is SubjectKind.JOB
            else EconomicComponent.SERVICE_LINE
        ),
        finding_type=(
            FindingType.JOB_ECONOMIC_READINESS
            if subject.subject_kind is SubjectKind.JOB
            else FindingType.SERVICE_LINE_READINESS
        ),
        state=state,
        confidence=confidence,
        measured_condition=(
            f"The explicit {subject.subject_kind.value} subject is {state.value} across "
            f"{len(component_findings)} required economic component(s)."
        ),
        evidence=tuple(sorted(evidence, key=lambda item: item.assertion_id)),
        limitations=tuple(
            sorted({limit for item in component_findings for limit in item.limitations})
        ),
        explanation_facts=tuple(
            f"{item.component.value}={item.state.value}"
            for item in sorted(
                component_findings, key=lambda item: item.component.value
            )
        ),
    )


def _component_finding(
    subject: FindingSubject,
    component: EconomicComponent,
    evidence: tuple[EvidenceAssertion, ...],
) -> EconomicInconsistencyFinding:
    if not evidence:
        return _build_finding(
            subject=subject,
            component=component,
            finding_type=_TYPE_BY_COMPONENT[component],
            state=FindingState.ABSENT,
            confidence=EvidenceConfidence.UNKNOWN,
            measured_condition=f"No {component.value} evidence is present for the explicit reconciliation key.",
            evidence=(),
            limitations=("missing_evidence_is_not_zero", "economic_analysis_not_ready"),
            explanation_facts=(
                "The owning domain supplied the subject key; no matching assertion exists.",
            ),
        )

    assessment = assess_source_conformance(evidence)
    conformance = next(
        item for item in assessment.findings if item.component is component
    )
    state = {
        EvidenceConfidence.AVAILABLE: FindingState.READY,
        EvidenceConfidence.PARTIAL: FindingState.PARTIAL,
        EvidenceConfidence.UNKNOWN: FindingState.UNKNOWN,
        EvidenceConfidence.CONFLICTING: FindingState.CONFLICTING,
    }[conformance.confidence]
    conditions = {
        FindingState.READY: "Evidence requirements are satisfied for later economic analysis.",
        FindingState.PARTIAL: "Evidence exists but required authority, reconciliation, or policy inputs are incomplete.",
        FindingState.UNKNOWN: "Source evidence is explicitly incomplete, so the economic condition is unknown.",
        FindingState.CONFLICTING: "Assertions sharing the reconciliation key report different immutable values.",
        FindingState.ABSENT: "Evidence is absent.",
    }
    limitations = tuple(
        sorted(
            {
                *(limit for item in evidence for limit in item.limitations),
                *(f"missing:{item}" for item in conformance.missing_requirements),
                "no_source_precedence_applied",
                "no_profit_calculated",
            }
        )
    )
    return _build_finding(
        subject=subject,
        component=component,
        finding_type=_TYPE_BY_COMPONENT[component],
        state=state,
        confidence=conformance.confidence,
        measured_condition=conditions[state],
        evidence=evidence,
        limitations=limitations,
        explanation_facts=(
            f"{len(evidence)} immutable assertion(s) were evaluated.",
            f"Conformance state is {conformance.confidence.value}.",
            "No source assertion was corrected, overridden, or interpreted as a monetary loss.",
        ),
    )


def _potential_leakage(finding: EconomicInconsistencyFinding) -> bool:
    return finding.component in {
        EconomicComponent.REVENUE,
        EconomicComponent.SETTLEMENT,
        EconomicComponent.DIRECT_MATERIAL,
        EconomicComponent.DIRECT_LABOR,
    } and finding.state in {
        FindingState.PARTIAL,
        FindingState.ABSENT,
        FindingState.CONFLICTING,
        FindingState.UNKNOWN,
    }


def _build_finding(
    *,
    subject: FindingSubject,
    component: EconomicComponent,
    finding_type: FindingType,
    state: FindingState,
    confidence: EvidenceConfidence,
    measured_condition: str,
    evidence: tuple[EvidenceAssertion, ...],
    limitations: tuple[str, ...],
    explanation_facts: tuple[str, ...],
) -> EconomicInconsistencyFinding:
    evidence_contract = tuple(
        FindingEvidence(
            assertion_id=item.assertion_id,
            source_system=item.source_system,
            source_authority=item.source_authority,
            confidence=item.confidence,
            evidence_digest=item.evidence_digest,
            value_digest=item.value_digest,
            package_digest=item.package_digest,
            limitations=item.limitations,
        )
        for item in evidence
    )
    canonical = {
        "definition_version": FINDING_DEFINITION_VERSION,
        "finding_type": finding_type.value,
        "subject_id": subject.subject_id,
        "reconciliation_key": subject.reconciliation_key,
        "component": component.value,
        "state": state.value,
        "confidence": confidence.value,
        "evidence": [
            {
                "assertion_id": item.assertion_id,
                "source_authority": item.source_authority,
                "confidence": item.confidence.value,
                "evidence_digest": item.evidence_digest,
                "value_digest": item.value_digest,
                "package_digest": item.package_digest,
                "limitations": item.limitations,
            }
            for item in evidence_contract
        ],
        "limitations": tuple(sorted(set(limitations))),
    }
    finding_id = (
        "eco-finding:"
        + hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return EconomicInconsistencyFinding(
        finding_id=finding_id,
        definition_version=FINDING_DEFINITION_VERSION,
        finding_type=finding_type,
        subject_id=subject.subject_id,
        reconciliation_key=subject.reconciliation_key,
        component=component,
        state=state,
        confidence=confidence,
        measured_condition=measured_condition,
        evidence=evidence_contract,
        source_authorities=tuple(sorted({item.source_authority for item in evidence})),
        limitations=tuple(sorted(set(limitations))),
        explanation_facts=explanation_facts,
    )
