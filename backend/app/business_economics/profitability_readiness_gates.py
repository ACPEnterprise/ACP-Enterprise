"""Deterministic gates from certified evidence to governed economic outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Final

GATE_CONTRACT_VERSION: Final = "economics.profitability-readiness-gates.v1"


class PrerequisiteState(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"
    POLICY_UNSELECTED = "POLICY_UNSELECTED"
    POLICY_UNCERTIFIED = "POLICY_UNCERTIFIED"
    ACCOUNTANT_INPUT_REQUIRED = "ACCOUNTANT_INPUT_REQUIRED"
    SOURCE_UNRECONCILED = "SOURCE_UNRECONCILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class GateState(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class EconomicPrerequisite:
    key: str
    state: PrerequisiteState
    evidence_digest: str | None
    authority: str
    limitation: str | None = None


_GATES: Final = {
    "DIRECT_CONTRIBUTION_READY": (
        "invoiced_revenue",
        "direct_wage_cost",
        "direct_material_cost",
        "other_direct_cost_completeness",
    ),
    "BURDENED_CONTRIBUTION_READY": (
        "invoiced_revenue",
        "direct_wage_cost",
        "direct_material_cost",
        "other_direct_cost_completeness",
        "employer_burden_components",
        "employer_burden_allocation_policy",
    ),
    "FULLY_LOADED_PROFIT_READY": (
        "burdened_contribution",
        "reconciled_overhead_evidence",
        "overhead_pool_policy",
        "overhead_allocation_policy",
    ),
    "COMPANY_BREAK_EVEN_READY": (
        "reconciled_overhead_evidence",
        "overhead_pool_policy",
        "overhead_allocation_policy",
        "productive_hour_definition",
        "productive_hours",
    ),
    "BRANCH_BREAK_EVEN_READY": (
        "company_break_even_inputs",
        "authoritative_branch_scope",
        "branch_allocation_policy",
        "branch_allocation_basis",
    ),
    "SERVICE_LINE_BREAK_EVEN_READY": (
        "company_break_even_inputs",
        "canonical_service_category",
        "service_line_allocation_policy",
        "service_line_allocation_basis",
    ),
    "TRUCK_CAPACITY_ECONOMICS_READY": (
        "measured_capacity_baseline",
        "authoritative_vehicle_cost",
        "authoritative_vehicle_job_relationship",
        "fleet_equipment_cost_policy",
        "capacity_buffer_policy",
    ),
}


def evaluate_profitability_gates(
    prerequisites: tuple[EconomicPrerequisite, ...],
) -> dict[str, object]:
    by_key = {item.key: item for item in prerequisites}
    gates: list[dict[str, object]] = []
    for gate, required in _GATES.items():
        blockers: list[dict[str, object]] = []
        evidence: list[str] = []
        for key in required:
            item = by_key.get(key)
            if item is None:
                blockers.append({"key": key, "state": "MISSING"})
            elif item.state not in {
                PrerequisiteState.AVAILABLE,
                PrerequisiteState.NOT_APPLICABLE,
            }:
                blockers.append(
                    {
                        "key": key,
                        "state": item.state.value,
                        "authority": item.authority,
                        "limitation": item.limitation,
                    }
                )
            elif item.evidence_digest:
                evidence.append(item.evidence_digest)
        gates.append(
            {
                "gate": gate,
                "state": GateState.BLOCKED.value if blockers else GateState.READY.value,
                "blockers": blockers,
                "evidence_digests": sorted(evidence),
            }
        )
    canonical = {"version": GATE_CONTRACT_VERSION, "gates": gates}
    return {
        **canonical,
        "readiness_digest": sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "missing_is_zero": False,
        "mutation_authority": "none",
    }
