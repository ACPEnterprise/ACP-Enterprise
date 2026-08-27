from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from .findings import EconomicInconsistencyFinding, FindingState, SubjectKind
from .source_conformance import EconomicComponent, EvidenceConfidence

MEASUREMENT_DEFINITION_VERSION = "eco.measurement.inputs.v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class MeasurementComponent(str, Enum):
    REVENUE_EARNED_VALUE = "revenue_earned_value"
    SETTLEMENT = "settlement"
    DIRECT_LABOR = "direct_labor"
    LABOR_BURDEN = "labor_burden_prerequisite"
    DIRECT_MATERIAL = "direct_material"
    MATERIAL_COSTING = "material_costing_prerequisite"
    OTHER_DIRECT_COST = "other_attributable_direct_cost"
    OVERHEAD_ALLOCATION = "overhead_allocation_prerequisite"
    JOB_CONTEXT = "job_identity_lifecycle_context"
    SERVICE_LINE_ATTRIBUTION = "service_line_category_attribution"
    ACCOUNTING_RECONCILIATION = "accounting_posting_reconciliation"


class MeasurementGateState(str, Enum):
    MEASURABLE = "measurable"
    PARTIALLY_MEASURABLE = "partially_measurable"
    NOT_MEASURABLE = "not_measurable"
    CONFLICTING = "conflicting"


class PrerequisiteState(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class MeasurementEvidenceInput:
    input_id: str
    subject_id: str
    reconciliation_key: str
    component: MeasurementComponent
    source_authority: str
    evidence_state: FindingState
    confidence: EvidenceConfidence
    source_value: Decimal | None
    currency: str | None
    unit: str | None
    effective_date: date | None
    as_of: datetime | None
    accepted_for_measurement: bool
    limitations: tuple[str, ...]
    evidence_digest: str
    value_digest: str
    package_digest: str
    definition_version: str = MEASUREMENT_DEFINITION_VERSION

    def __post_init__(self) -> None:
        if not self.input_id or not self.subject_id or not self.reconciliation_key:
            raise ValueError("measurement input identities are required")
        if not self.source_authority:
            raise ValueError("source authority is required")
        if self.definition_version != MEASUREMENT_DEFINITION_VERSION:
            raise ValueError("unsupported measurement input definition version")
        for digest in (self.evidence_digest, self.value_digest, self.package_digest):
            if not _SHA256.fullmatch(digest):
                raise ValueError("immutable measurement provenance is required")
        if self.source_value is not None and not (self.currency or self.unit):
            raise ValueError("a measured value requires currency or unit")
        if (
            self.source_authority == "quickbooks_online_source_reported"
            and self.accepted_for_measurement
        ):
            raise ValueError(
                "source-reported QBO evidence is not accepted economic truth"
            )
        if (
            self.accepted_for_measurement
            and self.evidence_state is not FindingState.READY
        ):
            raise ValueError("only ready evidence may be accepted for measurement")


@dataclass(frozen=True, slots=True)
class PolicyPrerequisite:
    dependency_id: str
    component: MeasurementComponent
    state: PrerequisiteState
    authority: str
    policy_version: str | None = None
    evidence_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.dependency_id or not self.authority:
            raise ValueError("policy dependency identity and authority are required")
        if self.state is PrerequisiteState.RESOLVED:
            if not self.policy_version or not self.evidence_digest:
                raise ValueError(
                    "resolved policy requires versioned authority evidence"
                )
            if not _SHA256.fullmatch(self.evidence_digest):
                raise ValueError("resolved policy evidence digest is invalid")
        elif self.policy_version or self.evidence_digest:
            raise ValueError("unresolved policy cannot imply a selected policy")


@dataclass(frozen=True, slots=True)
class ComponentMeasurementGate:
    component: MeasurementComponent
    state: FindingState
    evidence_ids: tuple[str, ...]
    source_authorities: tuple[str, ...]
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContributionMeasurementGate:
    gate_id: str
    definition_version: str
    subject_id: str
    subject_kind: SubjectKind
    reconciliation_key: str
    state: MeasurementGateState
    components: tuple[ComponentMeasurementGate, ...]
    evidence: tuple[MeasurementEvidenceInput, ...]
    policy_dependencies: tuple[PolicyPrerequisite, ...]
    blocking_components: tuple[MeasurementComponent, ...]
    explanation_facts: tuple[str, ...]


_VALUE_REQUIRED = {
    MeasurementComponent.REVENUE_EARNED_VALUE,
    MeasurementComponent.SETTLEMENT,
    MeasurementComponent.DIRECT_LABOR,
    MeasurementComponent.DIRECT_MATERIAL,
    MeasurementComponent.OTHER_DIRECT_COST,
}

_FINDING_COMPONENTS = {
    MeasurementComponent.REVENUE_EARNED_VALUE: EconomicComponent.REVENUE,
    MeasurementComponent.SETTLEMENT: EconomicComponent.SETTLEMENT,
    MeasurementComponent.DIRECT_LABOR: EconomicComponent.DIRECT_LABOR,
    MeasurementComponent.DIRECT_MATERIAL: EconomicComponent.DIRECT_MATERIAL,
    MeasurementComponent.OVERHEAD_ALLOCATION: EconomicComponent.OVERHEAD,
    MeasurementComponent.JOB_CONTEXT: EconomicComponent.JOB_IDENTITY,
    MeasurementComponent.SERVICE_LINE_ATTRIBUTION: EconomicComponent.SERVICE_LINE,
}


def evaluate_contribution_measurement_gate(
    *,
    subject_id: str,
    subject_kind: SubjectKind,
    reconciliation_key: str,
    required_components: tuple[MeasurementComponent, ...],
    evidence: tuple[MeasurementEvidenceInput, ...],
    findings: tuple[EconomicInconsistencyFinding, ...],
    policy_dependencies: tuple[PolicyPrerequisite, ...],
) -> ContributionMeasurementGate:
    if not subject_id or not reconciliation_key or not required_components:
        raise ValueError("subject, reconciliation key, and requirements are mandatory")
    if len(set(required_components)) != len(required_components):
        raise ValueError("required measurement components must be unique")
    relevant_evidence = tuple(
        sorted(
            (
                item
                for item in evidence
                if item.subject_id == subject_id
                and item.reconciliation_key == reconciliation_key
            ),
            key=lambda item: item.input_id,
        )
    )
    if len({item.input_id for item in relevant_evidence}) != len(relevant_evidence):
        raise ValueError("measurement input identities must be unique")
    relevant_findings = tuple(
        item
        for item in findings
        if item.subject_id == subject_id
        and item.reconciliation_key == reconciliation_key
    )
    policies = tuple(sorted(policy_dependencies, key=lambda item: item.dependency_id))
    component_gates = tuple(
        _component_gate(component, relevant_evidence, relevant_findings, policies)
        for component in sorted(required_components, key=lambda item: item.value)
    )
    if any(item.state is FindingState.CONFLICTING for item in component_gates):
        state = MeasurementGateState.CONFLICTING
    elif all(item.state is FindingState.READY for item in component_gates):
        state = MeasurementGateState.MEASURABLE
    elif any(item.state is FindingState.READY for item in component_gates):
        state = MeasurementGateState.PARTIALLY_MEASURABLE
    else:
        state = MeasurementGateState.NOT_MEASURABLE
    blocking = tuple(
        item.component
        for item in component_gates
        if item.state is not FindingState.READY
    )
    canonical = {
        "definition_version": MEASUREMENT_DEFINITION_VERSION,
        "subject_id": subject_id,
        "subject_kind": subject_kind.value,
        "reconciliation_key": reconciliation_key,
        "state": state.value,
        "components": [
            {
                "component": item.component.value,
                "state": item.state.value,
                "evidence_ids": item.evidence_ids,
                "blocking_reasons": item.blocking_reasons,
            }
            for item in component_gates
        ],
        "evidence": [
            {
                "input_id": item.input_id,
                "authority": item.source_authority,
                "state": item.evidence_state.value,
                "confidence": item.confidence.value,
                "value": str(item.source_value)
                if item.source_value is not None
                else None,
                "currency": item.currency,
                "unit": item.unit,
                "effective_date": item.effective_date.isoformat()
                if item.effective_date
                else None,
                "as_of": item.as_of.isoformat() if item.as_of else None,
                "accepted": item.accepted_for_measurement,
                "evidence_digest": item.evidence_digest,
                "value_digest": item.value_digest,
                "package_digest": item.package_digest,
                "definition_version": item.definition_version,
            }
            for item in relevant_evidence
        ],
        "policies": [
            {
                "dependency_id": item.dependency_id,
                "component": item.component.value,
                "state": item.state.value,
                "authority": item.authority,
                "policy_version": item.policy_version,
                "evidence_digest": item.evidence_digest,
            }
            for item in policies
        ],
    }
    gate_id = (
        "eco-measurement-gate:"
        + hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return ContributionMeasurementGate(
        gate_id=gate_id,
        definition_version=MEASUREMENT_DEFINITION_VERSION,
        subject_id=subject_id,
        subject_kind=subject_kind,
        reconciliation_key=reconciliation_key,
        state=state,
        components=component_gates,
        evidence=relevant_evidence,
        policy_dependencies=policies,
        blocking_components=blocking,
        explanation_facts=tuple(
            f"{item.component.value}={item.state.value}" for item in component_gates
        ),
    )


def _component_gate(
    component: MeasurementComponent,
    evidence: tuple[MeasurementEvidenceInput, ...],
    findings: tuple[EconomicInconsistencyFinding, ...],
    policies: tuple[PolicyPrerequisite, ...],
) -> ComponentMeasurementGate:
    selected = tuple(item for item in evidence if item.component is component)
    selected_policies = tuple(item for item in policies if item.component is component)
    reasons: set[str] = set()
    finding_component = _FINDING_COMPONENTS.get(component)
    if (
        finding_component is not None
        and any(
            item.state is FindingState.CONFLICTING
            and item.component is finding_component
            for item in findings
        )
        and selected
    ):
        reasons.add("source_conformance_finding_conflicting")
    if len({item.value_digest for item in selected}) > 1:
        reasons.add("evidence_values_conflict")
    if any(item.evidence_state is FindingState.CONFLICTING for item in selected):
        reasons.add("evidence_state_conflicting")
    if reasons:
        state = FindingState.CONFLICTING
    elif not selected:
        state = FindingState.ABSENT
        reasons.add("required_evidence_absent_not_zero")
    elif any(item.evidence_state is FindingState.UNKNOWN for item in selected):
        state = FindingState.UNKNOWN
        reasons.add("evidence_unknown")
    elif any(
        item.evidence_state is FindingState.PARTIAL or not item.accepted_for_measurement
        for item in selected
    ):
        state = FindingState.PARTIAL
        reasons.add("evidence_partial_or_unaccepted")
    elif component in _VALUE_REQUIRED and any(
        item.source_value is None for item in selected
    ):
        state = FindingState.PARTIAL
        reasons.add("measured_value_unavailable_not_zero")
    else:
        state = FindingState.READY
    if selected_policies and any(
        item.state is PrerequisiteState.UNRESOLVED for item in selected_policies
    ):
        if state is FindingState.READY:
            state = FindingState.PARTIAL
        reasons.add("required_policy_unresolved")
    return ComponentMeasurementGate(
        component=component,
        state=state,
        evidence_ids=tuple(item.input_id for item in selected),
        source_authorities=tuple(sorted({item.source_authority for item in selected})),
        blocking_reasons=tuple(sorted(reasons)),
    )
