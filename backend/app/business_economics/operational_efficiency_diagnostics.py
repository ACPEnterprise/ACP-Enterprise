"""Deterministic operational diagnostic evidence without causal conclusions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.operational_measurement.productive_hour_readiness import (
    MeasureReadiness,
    ProductiveHourMeasure,
    ProductiveHourReadinessPacket,
    ReadinessState,
)

DIAGNOSTICS_VERSION: Final = "eco.operational-efficiency-diagnostics.v1"
MAX_DIAGNOSTIC_INPUTS: Final = 100_000
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class DiagnosticKind(StrEnum):
    LOW_UTILIZATION = "low_utilization"
    EXCESSIVE_TRAVEL = "excessive_travel"
    LONG_JOB_DURATION = "long_job_duration"
    CALLBACK_REWORK = "callback_rework"
    LOW_CONVERSION = "low_conversion"
    DISPATCH_INEFFICIENCY = "dispatch_inefficiency"
    MATERIAL_LEAKAGE = "material_leakage"
    OVERHEAD_BURDEN = "overhead_burden"
    CAPACITY_IMBALANCE = "capacity_imbalance"
    MISSING_EVIDENCE = "missing_evidence"


class DiagnosticState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class DiagnosticEvidenceInput:
    evidence_id: str
    kind: DiagnosticKind
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID | None
    job_id: UUID | None
    reconciliation_key: str
    authority: str
    state: DiagnosticState
    observed_value: Decimal | None
    unit: str | None
    as_of: datetime | None
    evidence_digest: str
    value_digest: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.reconciliation_key or not self.authority:
            raise ValueError("diagnostic evidence identity and authority are required")
        if not _SHA256.fullmatch(self.evidence_digest) or not _SHA256.fullmatch(
            self.value_digest
        ):
            raise ValueError("immutable diagnostic evidence digest is required")
        if self.state is DiagnosticState.AVAILABLE and self.observed_value is None:
            raise ValueError("available diagnostic evidence requires an observed value")
        if self.observed_value is not None and not self.unit:
            raise ValueError("diagnostic observed value requires a unit")


@dataclass(frozen=True, slots=True)
class DiagnosticReadiness:
    kind: DiagnosticKind
    state: DiagnosticState
    evidence_ids: tuple[str, ...]
    source_authorities: tuple[str, ...]
    source_as_of: tuple[str, ...]
    observed_components: tuple[tuple[str, str | None, str | None], ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationalEfficiencyDiagnosticsPacket:
    contract_version: str
    company_id: UUID
    branch_id: UUID | None
    reconciliation_key: str
    productive_hour_evidence_digest: str
    diagnostics: tuple[DiagnosticReadiness, ...]
    policy_gates: tuple[str, ...]
    causal_conclusion: None
    employment_action: None
    recommendation: None
    packet_digest: str


POLICY_GATES: Final = (
    "utilization_threshold",
    "travel_threshold",
    "job_duration_comparison_method",
    "conversion_comparison_method",
    "overhead_allocation_method",
    "capacity_buffer_policy",
)


def operational_efficiency_diagnostics_contract() -> dict[str, object]:
    return {
        "contract_version": DIAGNOSTICS_VERSION,
        "diagnostics": tuple(item.value for item in DiagnosticKind),
        "interpretation": "observed_components_only",
        "policy_gates": POLICY_GATES,
        "causal_conclusion": None,
        "employment_action": None,
        "recommendation": None,
        "mutation_authority": "none",
    }


def build_operational_efficiency_diagnostics(
    productive_hours: ProductiveHourReadinessPacket,
    *,
    reconciliation_key: str,
    evidence: tuple[DiagnosticEvidenceInput, ...] = (),
    branch_id: UUID | None = None,
) -> OperationalEfficiencyDiagnosticsPacket:
    if not reconciliation_key:
        raise ValueError("diagnostic reconciliation key is required")
    if len(evidence) > MAX_DIAGNOSTIC_INPUTS:
        raise ValueError("diagnostic evidence input exceeds bounded size")
    if any(item.company_id != productive_hours.company_id for item in evidence):
        raise ValueError("foreign Company diagnostic evidence")
    if branch_id is None and any(item.branch_id is not None for item in evidence):
        raise ValueError(
            "Company diagnostics cannot silently aggregate Branch evidence"
        )
    if branch_id is not None and any(item.branch_id != branch_id for item in evidence):
        raise ValueError("foreign Branch diagnostic evidence")
    if any(item.reconciliation_key != reconciliation_key for item in evidence):
        raise ValueError("mixed diagnostic reconciliation period")
    if len({item.evidence_id for item in evidence}) != len(evidence):
        raise ValueError("duplicate diagnostic evidence identity")

    scope = (
        next((x for x in productive_hours.branches if x.branch_id == branch_id), None)
        if branch_id
        else productive_hours.company
    )
    if scope is None:
        raise ValueError("Branch lacks productive-hour scope")
    diagnostics = tuple(
        _diagnostic(kind, evidence, scope.measures) for kind in DiagnosticKind
    )
    canonical = {
        "contract_version": DIAGNOSTICS_VERSION,
        "company_id": str(productive_hours.company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "reconciliation_key": reconciliation_key,
        "productive_hour_evidence_digest": productive_hours.evidence_digest,
        "diagnostics": [asdict(item) for item in diagnostics],
        "policy_gates": POLICY_GATES,
        "causal_conclusion": None,
        "employment_action": None,
        "recommendation": None,
    }
    return OperationalEfficiencyDiagnosticsPacket(
        DIAGNOSTICS_VERSION,
        productive_hours.company_id,
        branch_id,
        reconciliation_key,
        productive_hours.evidence_digest,
        diagnostics,
        POLICY_GATES,
        None,
        None,
        None,
        _digest(canonical),
    )


def _diagnostic(
    kind: DiagnosticKind,
    evidence: tuple[DiagnosticEvidenceInput, ...],
    measures: tuple[MeasureReadiness, ...],
) -> DiagnosticReadiness:
    selected = tuple(
        sorted((x for x in evidence if x.kind is kind), key=lambda x: x.evidence_id)
    )
    components: list[tuple[str, str | None, str | None]] = []
    limitations = {limit for item in selected for limit in item.limitations}
    if kind is DiagnosticKind.LOW_UTILIZATION:
        _add_measure(components, measures, ProductiveHourMeasure.PRODUCTIVE_JOB_MINUTES)
        _add_measure(components, measures, ProductiveHourMeasure.PAID_MINUTES)
        limitations.add("No low-utilization threshold or cause is selected.")
    elif kind is DiagnosticKind.EXCESSIVE_TRAVEL:
        _add_measure(components, measures, ProductiveHourMeasure.TRAVEL_MINUTES)
        limitations.add("No excessive-travel threshold or Employee fault is inferred.")
    elif kind is DiagnosticKind.LONG_JOB_DURATION:
        _add_measure(components, measures, ProductiveHourMeasure.ACTUAL_WORKED_MINUTES)
        limitations.add("Actual worked duration is not replaced by scheduled duration.")
    elif kind is DiagnosticKind.CAPACITY_IMBALANCE:
        for measure in (
            ProductiveHourMeasure.PAID_MINUTES,
            ProductiveHourMeasure.PRODUCTIVE_JOB_MINUTES,
            ProductiveHourMeasure.UNCLASSIFIED_PAID_MINUTES,
        ):
            _add_measure(components, measures, measure)
        limitations.add("No capacity target, buffer, or staffing action is selected.")
    elif kind is DiagnosticKind.MISSING_EVIDENCE:
        for item in measures:
            if item.state is not ReadinessState.AVAILABLE:
                components.append((item.measure.value, None, item.state.value))
        limitations.add("Missing evidence is reported, never converted to zero.")

    by_semantic: dict[tuple[UUID | None, UUID | None], set[str]] = {}
    for evidence_item in selected:
        by_semantic.setdefault(
            (evidence_item.employee_id, evidence_item.job_id), set()
        ).add(evidence_item.value_digest)
        components.append(
            (
                evidence_item.evidence_id,
                str(evidence_item.observed_value)
                if evidence_item.observed_value is not None
                else None,
                evidence_item.unit,
            )
        )
    conflict = any(len(values) > 1 for values in by_semantic.values()) or any(
        x.state is DiagnosticState.CONFLICTING for x in selected
    )
    states = [x.state for x in selected]
    measure_states = [
        component[2]
        for component in components
        if component[0] in {x.value for x in ProductiveHourMeasure}
    ]
    if conflict:
        state = DiagnosticState.CONFLICTING
    elif selected:
        state = (
            DiagnosticState.AVAILABLE
            if all(x is DiagnosticState.AVAILABLE for x in states)
            else DiagnosticState.PARTIAL
        )
    elif kind is DiagnosticKind.MISSING_EVIDENCE and components:
        state = DiagnosticState.AVAILABLE
    elif measure_states:
        state = (
            DiagnosticState.AVAILABLE
            if all(x == "AVAILABLE" for x in measure_states)
            else DiagnosticState.PARTIAL
        )
    else:
        state = DiagnosticState.ABSENT
        limitations.add(
            "Authoritative diagnostic evidence is absent; no condition or cause is asserted."
        )
    return DiagnosticReadiness(
        kind,
        state,
        tuple(x.evidence_id for x in selected),
        tuple(sorted({x.authority for x in selected})),
        tuple(sorted({x.as_of.isoformat() for x in selected if x.as_of})),
        tuple(components),
        tuple(sorted(limitations)),
    )


def _add_measure(
    components: list[tuple[str, str | None, str | None]],
    measures: tuple[MeasureReadiness, ...],
    measure: ProductiveHourMeasure,
) -> None:
    item = next(x for x in measures if x.measure is measure)
    components.append(
        (
            measure.value,
            str(item.minutes) if item.minutes is not None else None,
            item.state.value,
        )
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
