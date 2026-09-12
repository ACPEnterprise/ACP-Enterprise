"""Deterministic explanations and owner policy readiness without advice."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

from .break_even_calculation import (
    CalculationState,
    GovernedBreakEvenCalculation,
    ValueClass,
)
from .break_even_policy import (
    BreakEvenPolicyKind,
    BreakEvenPolicySnapshot,
    break_even_policy_decisions,
)

EXPLANATION_VERSION: Final = "eco.break-even-explanation.v1"


class OwnerDecisionState(StrEnum):
    SELECTED_APPROVED = "SELECTED_APPROVED"
    UNSELECTED = "UNSELECTED"


@dataclass(frozen=True, slots=True)
class ChangeExplanation:
    metric: str
    statement: str
    causing_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BreakEvenExplanation:
    contract_version: str
    calculation_digest: str
    calculation_state: CalculationState
    what_changed: tuple[ChangeExplanation, ...]
    measured_values: tuple[str, ...]
    policy_values: tuple[str, ...]
    scenario_values: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    blocked_because: tuple[str, ...]
    availability_requirements: tuple[str, ...]
    recommendation: None
    explanation_digest: str


@dataclass(frozen=True, slots=True)
class OwnerPolicyDecisionReadiness:
    policy_family: BreakEvenPolicyKind
    current_state: OwnerDecisionState
    why_it_matters: str
    supported_options: tuple[str, ...]
    value_type: str
    data_prerequisites: tuple[str, ...]
    downstream_effect: str


@dataclass(frozen=True, slots=True)
class OwnerPolicySelectionPacket:
    contract_version: str
    decisions: tuple[OwnerPolicyDecisionReadiness, ...]
    owner_selection_required: tuple[BreakEvenPolicyKind, ...]
    recommendation: None
    packet_digest: str


_WHY = {
    kind: f"Controls the governed {kind.value.replace('_', ' ')} treatment in calculated economics."
    for kind in BreakEvenPolicyKind
}
_PREREQUISITES: dict[BreakEvenPolicyKind, tuple[str, ...]] = {
    BreakEvenPolicyKind.PRODUCTIVE_HOUR_DEFINITION: (
        "accepted Employee/Job time evidence",
    ),
    BreakEvenPolicyKind.LABOR_BURDEN_METHOD: (
        "authoritative employer-cost components or approved rate basis",
    ),
    BreakEvenPolicyKind.OVERHEAD_ALLOCATION_METHOD: (
        "accepted overhead pool and candidate allocation drivers",
    ),
    BreakEvenPolicyKind.ALLOCATION_SCOPE: (
        "authoritative Company and Branch identity",
    ),
    BreakEvenPolicyKind.OVERHEAD_CLASSIFICATION: (
        "account/category classification evidence",
    ),
    BreakEvenPolicyKind.OWNER_COMPENSATION_TREATMENT: (
        "authoritative owner compensation evidence",
    ),
    BreakEvenPolicyKind.VEHICLE_EQUIPMENT_COST_TREATMENT: (
        "authoritative Fleet/equipment costs",
    ),
    BreakEvenPolicyKind.MATERIAL_COSTING_BASIS: (
        "actual consumption and acquisition/cost-layer evidence",
    ),
    BreakEvenPolicyKind.LABOR_CLASSIFICATION: (
        "accepted Job attribution and role evidence",
    ),
    BreakEvenPolicyKind.CALLBACK_REWORK_TREATMENT: (
        "authoritative originating/corrective Job relationship",
    ),
    BreakEvenPolicyKind.MARKETING_ALLOCATION: (
        "authoritative marketing cost and allocation dimensions",
    ),
    BreakEvenPolicyKind.TARGET_GROSS_MARGIN: ("owner-approved target only",),
    BreakEvenPolicyKind.TARGET_OPERATING_MARGIN: ("owner-approved target only",),
    BreakEvenPolicyKind.CAPACITY_BUFFER: (
        "accepted available/productive capacity evidence",
    ),
    BreakEvenPolicyKind.UNPRODUCTIVE_TIME_TREATMENT: (
        "accepted paid and classified operational time",
    ),
    BreakEvenPolicyKind.OVERTIME_PREMIUM_TREATMENT: (
        "accepted overtime and premium cost evidence",
    ),
    BreakEvenPolicyKind.SERVICE_LINE_ALLOCATION: (
        "authoritative service-line identity and driver evidence",
    ),
    BreakEvenPolicyKind.ROUNDING_RULE: (
        "currency and reporting precision requirements",
    ),
}


def explain_break_even_calculation(
    calculation: GovernedBreakEvenCalculation,
) -> BreakEvenExplanation:
    changes = tuple(
        ChangeExplanation(
            item.metric,
            f"Scenario changes {item.metric} by {item.delta} {item.unit} from the measured baseline calculation.",
            (item.metric,),
        )
        for item in calculation.scenario_deltas
        if item.delta != 0
    )
    measured = sorted(
        {
            component.name
            for result in (*calculation.baseline_results, *calculation.scenario_results)
            for component in result.components
            if component.value_class is ValueClass.MEASURED_FACT
        }
    )
    scenario = sorted(
        {
            component.name
            for result in calculation.scenario_results
            for component in result.components
            if component.value_class is ValueClass.SCENARIO_ASSUMPTION
        }
    )
    missing = tuple(
        x.removeprefix("missing_evidence:")
        for x in calculation.blockers
        if x.startswith("missing_evidence:")
    )
    requirements = tuple(_requirement(blocker) for blocker in calculation.blockers)
    policy_values = tuple(item[0] for item in calculation.policy_references)
    body = {
        "contract_version": EXPLANATION_VERSION,
        "calculation_digest": calculation.calculation_digest,
        "calculation_state": calculation.state,
        "what_changed": [asdict(x) for x in changes],
        "measured_values": measured,
        "policy_values": policy_values,
        "scenario_values": scenario,
        "missing_evidence": missing,
        "blocked_because": calculation.blockers,
        "availability_requirements": requirements,
        "recommendation": None,
    }
    return BreakEvenExplanation(
        EXPLANATION_VERSION,
        calculation.calculation_digest,
        calculation.state,
        changes,
        tuple(measured),
        policy_values,
        tuple(scenario),
        missing,
        calculation.blockers,
        requirements,
        None,
        _digest(body),
    )


def build_owner_policy_selection_packet(
    policy: BreakEvenPolicySnapshot,
) -> OwnerPolicySelectionPacket:
    policy.verify()
    selected = {item.kind for item in policy.selections}
    contract = break_even_policy_decisions()
    decisions = tuple(
        OwnerPolicyDecisionReadiness(
            kind,
            OwnerDecisionState.SELECTED_APPROVED
            if kind in selected
            else OwnerDecisionState.UNSELECTED,
            _WHY[kind],
            contract[kind]["supported_options"],  # type: ignore[arg-type]
            str(contract[kind]["value_type"]),
            _PREREQUISITES[kind],
            f"Controls calculated results that depend on {kind.value}; it creates no recommendation.",
        )
        for kind in BreakEvenPolicyKind
    )
    missing = tuple(
        item.policy_family
        for item in decisions
        if item.current_state is OwnerDecisionState.UNSELECTED
    )
    body = {
        "contract_version": EXPLANATION_VERSION,
        "decisions": [asdict(x) for x in decisions],
        "owner_selection_required": missing,
        "recommendation": None,
    }
    return OwnerPolicySelectionPacket(
        EXPLANATION_VERSION, decisions, missing, None, _digest(body)
    )


def _requirement(blocker: str) -> str:
    if blocker.startswith("missing_policy:"):
        return (
            "Obtain explicit owner/accountant approval for "
            + blocker.split(":", 1)[1]
            + "."
        )
    if blocker.startswith("missing_evidence:"):
        return (
            "Admit authoritative measured evidence for "
            + blocker.split(":", 1)[1]
            + "."
        )
    if blocker.startswith("conflicting_evidence:"):
        return (
            "Resolve conflicting source evidence for " + blocker.split(":", 1)[1] + "."
        )
    return "Resolve calculation gate: " + blocker + "."


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
