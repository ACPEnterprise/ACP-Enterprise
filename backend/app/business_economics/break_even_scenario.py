"""Deterministic, non-mutating break-even scenario evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from .break_even_policy import (
    BreakEvenPolicyKind,
    BreakEvenPolicySnapshot,
)

MODEL_VERSION: Final = "eco.break-even-scenario-model.v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ScenarioMetric(StrEnum):
    PRODUCTIVE_HOURS = "productive_hours"
    EARNED_REVENUE = "earned_revenue"
    DIRECT_LABOR_COST = "direct_labor_cost"
    LABOR_BURDEN_COST = "labor_burden_cost"
    DIRECT_MATERIAL_COST = "direct_material_cost"
    OTHER_DIRECT_COST = "other_direct_cost"
    FIXED_OVERHEAD = "fixed_overhead"
    VARIABLE_OVERHEAD = "variable_overhead"
    AVERAGE_TICKET = "average_ticket"
    CLOSE_RATE = "close_rate"
    OPPORTUNITY_COUNT = "opportunity_count"


@dataclass(frozen=True, slots=True)
class MeasuredScenarioFact:
    metric: ScenarioMetric
    value: Decimal | None
    unit: str
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    authority: str
    evidence_digest: str
    conflicting: bool = False

    def verify(self) -> None:
        if not self.authority or not _SHA256.fullmatch(self.evidence_digest):
            raise ValueError("measured fact authority and digest are required")
        if self.period_start > self.period_end:
            raise ValueError("measured fact period is inverted")


@dataclass(frozen=True, slots=True)
class ScenarioAssumption:
    metric: ScenarioMetric
    value: Decimal
    unit: str
    rationale: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.rationale or not self.provenance:
            raise ValueError("scenario assumption must be explicit and attributable")


@dataclass(frozen=True, slots=True)
class CalculatedResult:
    metric: str
    value: Decimal
    unit: str
    formula: str


@dataclass(frozen=True, slots=True)
class BreakEvenScenarioResult:
    model_version: str
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    measured_facts: tuple[MeasuredScenarioFact, ...]
    policy_inputs: tuple[tuple[str, str, int, str], ...]
    scenario_assumptions: tuple[ScenarioAssumption, ...]
    calculated_results: tuple[CalculatedResult, ...]
    recommendation: None
    mutation_authority: str
    result_digest: str


class ScenarioCalculationBlocked(ValueError):
    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = blockers
        super().__init__("break-even scenario blocked: " + ", ".join(blockers))


def evaluate_break_even_scenario(
    *,
    policy: BreakEvenPolicySnapshot,
    measured_facts: tuple[MeasuredScenarioFact, ...],
    assumptions: tuple[ScenarioAssumption, ...] = (),
) -> BreakEvenScenarioResult:
    policy.verify()
    blockers = [f"missing_policy:{kind.value}" for kind in policy.missing_policy]
    if not measured_facts:
        blockers.append("missing_measured_facts")
    for item in measured_facts:
        item.verify()
        if item.company_id != policy.company_id or item.branch_id != policy.branch_id:
            raise ValueError("foreign Company/Branch measured fact")
    periods = {(x.period_start, x.period_end) for x in measured_facts}
    if len(periods) > 1:
        raise ValueError("mixed measured periods")
    by_metric: dict[ScenarioMetric, list[MeasuredScenarioFact]] = {}
    for item in measured_facts:
        by_metric.setdefault(item.metric, []).append(item)
        if item.conflicting:
            blockers.append(f"conflicting_evidence:{item.metric.value}")
        elif item.value is None:
            blockers.append(f"missing_evidence:{item.metric.value}")
    required = {
        ScenarioMetric.PRODUCTIVE_HOURS,
        ScenarioMetric.EARNED_REVENUE,
        ScenarioMetric.DIRECT_LABOR_COST,
        ScenarioMetric.LABOR_BURDEN_COST,
        ScenarioMetric.DIRECT_MATERIAL_COST,
        ScenarioMetric.OTHER_DIRECT_COST,
        ScenarioMetric.FIXED_OVERHEAD,
        ScenarioMetric.VARIABLE_OVERHEAD,
    }
    blockers.extend(
        f"missing_evidence:{x.value}"
        for x in sorted(required - set(by_metric), key=lambda x: x.value)
    )
    if any(len(items) != 1 for items in by_metric.values()):
        blockers.append("duplicate_measured_metric")
    if len({x.metric for x in assumptions}) != len(assumptions):
        blockers.append("duplicate_scenario_assumption")
    if blockers:
        raise ScenarioCalculationBlocked(tuple(sorted(set(blockers))))

    values = {kind: items[0].value for kind, items in by_metric.items()}
    for assumption in assumptions:
        values[assumption.metric] = assumption.value
    if {
        ScenarioMetric.AVERAGE_TICKET,
        ScenarioMetric.CLOSE_RATE,
    } & {item.metric for item in assumptions}:
        required_revenue_inputs = {
            ScenarioMetric.AVERAGE_TICKET,
            ScenarioMetric.CLOSE_RATE,
            ScenarioMetric.OPPORTUNITY_COUNT,
        }
        unavailable = required_revenue_inputs - {
            key for key, value in values.items() if value is not None
        }
        if unavailable:
            raise ScenarioCalculationBlocked(
                tuple(
                    f"revenue_scenario_requires:{item.value}"
                    for item in sorted(unavailable, key=lambda item: item.value)
                )
            )
        average_ticket = values[ScenarioMetric.AVERAGE_TICKET]
        close_rate = values[ScenarioMetric.CLOSE_RATE]
        opportunity_count = values[ScenarioMetric.OPPORTUNITY_COUNT]
        assert average_ticket is not None
        assert close_rate is not None
        assert opportunity_count is not None
        values[ScenarioMetric.EARNED_REVENUE] = (
            average_ticket * close_rate * opportunity_count
        )
    assert all(value is not None for value in values.values())
    numeric = {key: value for key, value in values.items() if value is not None}
    hours = numeric[ScenarioMetric.PRODUCTIVE_HOURS]
    revenue = numeric[ScenarioMetric.EARNED_REVENUE]
    if hours <= 0:
        raise ScenarioCalculationBlocked(("productive_hours_must_be_positive",))
    variable_cost = sum(
        (
            numeric[x]
            for x in (
                ScenarioMetric.DIRECT_LABOR_COST,
                ScenarioMetric.LABOR_BURDEN_COST,
                ScenarioMetric.DIRECT_MATERIAL_COST,
                ScenarioMetric.OTHER_DIRECT_COST,
                ScenarioMetric.VARIABLE_OVERHEAD,
            )
        ),
        Decimal(0),
    )
    contribution = revenue - variable_cost
    if contribution <= 0:
        raise ScenarioCalculationBlocked(("positive_measured_contribution_required",))
    contribution_per_hour = contribution / hours
    fixed = numeric[ScenarioMetric.FIXED_OVERHEAD]
    break_even_hours = fixed / contribution_per_hour
    break_even_revenue = fixed / (contribution / revenue) if revenue > 0 else Decimal(0)
    rounding = str(_policy_value(policy, BreakEvenPolicyKind.ROUNDING_RULE))
    gross_target = Decimal(
        str(_policy_value(policy, BreakEvenPolicyKind.TARGET_GROSS_MARGIN))
    )
    operating_target = Decimal(
        str(_policy_value(policy, BreakEvenPolicyKind.TARGET_OPERATING_MARGIN))
    )
    direct_cost = sum(
        (
            numeric[ScenarioMetric.DIRECT_LABOR_COST],
            numeric[ScenarioMetric.LABOR_BURDEN_COST],
            numeric[ScenarioMetric.DIRECT_MATERIAL_COST],
            numeric[ScenarioMetric.OTHER_DIRECT_COST],
        ),
        Decimal(0),
    )
    results = (
        CalculatedResult(
            "measured_contribution",
            _round(contribution, rounding),
            "currency",
            "earned_revenue - measured_variable_costs",
        ),
        CalculatedResult(
            "contribution_per_productive_hour",
            _round(contribution_per_hour, rounding),
            "currency/hour",
            "measured_contribution / productive_hours",
        ),
        CalculatedResult(
            "break_even_productive_hours",
            _round(break_even_hours, rounding),
            "hour",
            "fixed_overhead / contribution_per_productive_hour",
        ),
        CalculatedResult(
            "break_even_revenue",
            _round(break_even_revenue, rounding),
            "currency",
            "fixed_overhead / measured_contribution_margin_ratio",
        ),
        CalculatedResult(
            "policy_target_gross_margin_revenue",
            _round(direct_cost / (Decimal(1) - gross_target), rounding),
            "currency",
            "measured_direct_cost / (1 - policy_target_gross_margin)",
        ),
        CalculatedResult(
            "policy_target_operating_margin_revenue",
            _round((variable_cost + fixed) / (Decimal(1) - operating_target), rounding),
            "currency",
            "measured_total_cost / (1 - policy_target_operating_margin)",
        ),
    )
    start, end = next(iter(periods))
    policy_inputs = tuple(
        (x.kind.value, str(x.value), x.version, x.policy_digest)
        for x in policy.selections
    )
    canonical = {
        "model_version": MODEL_VERSION,
        "company_id": policy.company_id,
        "branch_id": policy.branch_id,
        "period_start": start,
        "period_end": end,
        "measured_facts": [asdict(x) for x in measured_facts],
        "policy_inputs": policy_inputs,
        "scenario_assumptions": [asdict(x) for x in assumptions],
        "calculated_results": [asdict(x) for x in results],
        "recommendation": None,
        "mutation_authority": "none",
    }
    return BreakEvenScenarioResult(
        MODEL_VERSION,
        policy.company_id,
        policy.branch_id,
        start,
        end,
        measured_facts,
        policy_inputs,
        assumptions,
        results,
        None,
        "none",
        _digest(canonical),
    )


def _policy_value(policy: BreakEvenPolicySnapshot, kind: BreakEvenPolicyKind) -> object:
    return next(x.value for x in policy.selections if x.kind is kind)


def _round(value: Decimal, rule: str) -> Decimal:
    if rule == "no_intermediate_rounding":
        return value
    mode = ROUND_HALF_UP if rule == "currency_half_up" else ROUND_HALF_EVEN
    return value.quantize(Decimal("0.01"), rounding=mode)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
