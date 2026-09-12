"""Governed break-even calculations with component-level source lineage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from .break_even_policy import BreakEvenPolicyKind, BreakEvenPolicySnapshot
from .break_even_scenario import (
    MeasuredScenarioFact,
    ScenarioAssumption,
    ScenarioCalculationBlocked,
    ScenarioMetric,
    evaluate_break_even_scenario,
)

ENGINE_VERSION: Final = "eco.break-even-calculation.v1"


class CalculationState(StrEnum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"


class ValueClass(StrEnum):
    MEASURED_FACT = "MEASURED_FACT"
    POLICY_INPUT = "POLICY_INPUT"
    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    CALCULATED_RESULT = "CALCULATED_RESULT"


@dataclass(frozen=True, slots=True)
class ScenarioIdentity:
    scenario_id: UUID
    version: int
    label: str

    def __post_init__(self) -> None:
        if self.version < 1 or not self.label:
            raise ValueError("scenario identity requires version and label")


@dataclass(frozen=True, slots=True)
class ComponentTrace:
    name: str
    value: Decimal
    unit: str
    value_class: ValueClass
    source_reference: str


@dataclass(frozen=True, slots=True)
class EconomicCalculationValue:
    name: str
    value: Decimal
    unit: str
    formula: str
    components: tuple[ComponentTrace, ...]


@dataclass(frozen=True, slots=True)
class ScenarioDelta:
    metric: str
    baseline: Decimal
    scenario: Decimal
    delta: Decimal
    unit: str


@dataclass(frozen=True, slots=True)
class GovernedBreakEvenCalculation:
    contract_version: str
    state: CalculationState
    company_id: UUID
    branch_id: UUID | None
    service_line: str | None
    period_start: date | None
    period_end: date | None
    measurement_evidence_digests: tuple[str, ...]
    policy_references: tuple[tuple[str, str, int], ...]
    scenario_id: UUID | None
    scenario_version: int | None
    baseline_results: tuple[EconomicCalculationValue, ...]
    scenario_results: tuple[EconomicCalculationValue, ...]
    scenario_deltas: tuple[ScenarioDelta, ...]
    blockers: tuple[str, ...]
    scenario_is_measured_actual: bool
    recommendation: None
    calculation_digest: str


def calculate_governed_break_even(
    *,
    policy: BreakEvenPolicySnapshot,
    measured_facts: tuple[MeasuredScenarioFact, ...],
    scenario: ScenarioIdentity | None = None,
    assumptions: tuple[ScenarioAssumption, ...] = (),
    service_line: str | None = None,
) -> GovernedBreakEvenCalculation:
    """Calculate or return an exact BLOCKED packet; never selects missing policy."""
    if assumptions and scenario is None:
        raise ValueError("scenario assumptions require versioned scenario identity")
    if scenario is not None and not assumptions:
        raise ValueError("scenario identity requires explicit assumptions")
    policy.verify()
    for fact in measured_facts:
        fact.verify()
        if fact.company_id != policy.company_id or fact.branch_id != policy.branch_id:
            raise ValueError("foreign Company/Branch calculation evidence")
    periods = {(fact.period_start, fact.period_end) for fact in measured_facts}
    if len(periods) > 1:
        raise ValueError("mixed calculation evidence periods")
    scope_blockers = _scope_blockers(policy, service_line)
    try:
        evaluate_break_even_scenario(policy=policy, measured_facts=measured_facts)
    except ScenarioCalculationBlocked as error:
        return _blocked(
            policy, measured_facts, (*scope_blockers, *error.blockers), service_line
        )
    if scope_blockers:
        return _blocked(policy, measured_facts, scope_blockers, service_line)

    baseline_values = _economic_values(policy, measured_facts, ())
    scenario_values: tuple[EconomicCalculationValue, ...] = ()
    deltas: tuple[ScenarioDelta, ...] = ()
    if scenario is not None:
        try:
            evaluate_break_even_scenario(
                policy=policy, measured_facts=measured_facts, assumptions=assumptions
            )
        except ScenarioCalculationBlocked as error:
            return _blocked(
                policy, measured_facts, error.blockers, service_line, scenario
            )
        scenario_values = _economic_values(policy, measured_facts, assumptions)
        deltas = _deltas(baseline_values, scenario_values, measured_facts, assumptions)
    start, end = next(iter(periods))
    policy_refs = _policy_refs(policy)
    canonical = {
        "contract_version": ENGINE_VERSION,
        "state": CalculationState.AVAILABLE,
        "company_id": policy.company_id,
        "branch_id": policy.branch_id,
        "service_line": service_line,
        "period_start": start,
        "period_end": end,
        "evidence_digests": sorted(f.evidence_digest for f in measured_facts),
        "policy_references": policy_refs,
        "scenario_id": scenario.scenario_id if scenario else None,
        "scenario_version": scenario.version if scenario else None,
        "baseline_results": [asdict(x) for x in baseline_values],
        "scenario_results": [asdict(x) for x in scenario_values],
        "scenario_deltas": [asdict(x) for x in deltas],
        "scenario_is_measured_actual": False,
        "recommendation": None,
    }
    return GovernedBreakEvenCalculation(
        ENGINE_VERSION,
        CalculationState.AVAILABLE,
        policy.company_id,
        policy.branch_id,
        service_line,
        start,
        end,
        tuple(sorted(f.evidence_digest for f in measured_facts)),
        policy_refs,
        scenario.scenario_id if scenario else None,
        scenario.version if scenario else None,
        baseline_values,
        scenario_values,
        deltas,
        (),
        False,
        None,
        _digest(canonical),
    )


def _economic_values(
    policy: BreakEvenPolicySnapshot,
    facts: tuple[MeasuredScenarioFact, ...],
    assumptions: tuple[ScenarioAssumption, ...],
) -> tuple[EconomicCalculationValue, ...]:
    measured = {item.metric: item for item in facts}
    values = {kind: item.value for kind, item in measured.items()}
    for item in assumptions:
        values[item.metric] = item.value
    get = lambda metric: _required(values, metric)
    labor, burden = (
        get(ScenarioMetric.DIRECT_LABOR_COST),
        get(ScenarioMetric.LABOR_BURDEN_COST),
    )
    material, other = (
        get(ScenarioMetric.DIRECT_MATERIAL_COST),
        get(ScenarioMetric.OTHER_DIRECT_COST),
    )
    fixed, variable = (
        get(ScenarioMetric.FIXED_OVERHEAD),
        get(ScenarioMetric.VARIABLE_OVERHEAD),
    )
    hours, revenue = (
        get(ScenarioMetric.PRODUCTIVE_HOURS),
        get(ScenarioMetric.EARNED_REVENUE),
    )
    if (
        ScenarioMetric.AVERAGE_TICKET in values
        and ScenarioMetric.CLOSE_RATE in values
        and ScenarioMetric.OPPORTUNITY_COUNT in values
        and any(
            x.metric in {ScenarioMetric.AVERAGE_TICKET, ScenarioMetric.CLOSE_RATE}
            for x in assumptions
        )
    ):
        revenue = (
            get(ScenarioMetric.AVERAGE_TICKET)
            * get(ScenarioMetric.CLOSE_RATE)
            * get(ScenarioMetric.OPPORTUNITY_COUNT)
        )
    direct = labor + burden + material + other
    overhead = fixed + variable
    total = direct + overhead
    contribution = revenue - (direct + variable)
    contribution_margin = contribution / revenue if revenue else Decimal(0)
    gross = revenue - direct
    operating = revenue - total
    trace = lambda metric: _trace(metric, measured, assumptions)
    cost_components = (
        trace(ScenarioMetric.DIRECT_LABOR_COST),
        trace(ScenarioMetric.LABOR_BURDEN_COST),
        trace(ScenarioMetric.DIRECT_MATERIAL_COST),
        trace(ScenarioMetric.OTHER_DIRECT_COST),
        trace(ScenarioMetric.VARIABLE_OVERHEAD),
    )
    revenue_components = (
        (
            trace(ScenarioMetric.AVERAGE_TICKET),
            trace(ScenarioMetric.CLOSE_RATE),
            trace(ScenarioMetric.OPPORTUNITY_COUNT),
        )
        if any(
            x.metric in {ScenarioMetric.AVERAGE_TICKET, ScenarioMetric.CLOSE_RATE}
            for x in assumptions
        )
        else (trace(ScenarioMetric.EARNED_REVENUE),)
    )
    break_even_components = (
        trace(ScenarioMetric.FIXED_OVERHEAD),
        *revenue_components,
        *cost_components,
    )
    results = (
        _value(
            "total_direct_labor_cost",
            labor,
            "USD",
            "direct_labor_cost",
            (trace(ScenarioMetric.DIRECT_LABOR_COST),),
        ),
        _value(
            "labor_burden",
            burden,
            "USD",
            "accepted_or_policy-governed_burden",
            (trace(ScenarioMetric.LABOR_BURDEN_COST),),
        ),
        _value(
            "direct_material_cost",
            material,
            "USD",
            "accepted_material_cost",
            (trace(ScenarioMetric.DIRECT_MATERIAL_COST),),
        ),
        _value(
            "other_attributable_direct_cost",
            other,
            "USD",
            "accepted_other_direct_cost",
            (trace(ScenarioMetric.OTHER_DIRECT_COST),),
        ),
        _value(
            "allocated_overhead",
            overhead,
            "USD",
            _overhead_formula(policy),
            (
                trace(ScenarioMetric.FIXED_OVERHEAD),
                trace(ScenarioMetric.VARIABLE_OVERHEAD),
            ),
        ),
        _value(
            "total_operating_cost",
            total,
            "USD",
            "direct_costs + allocated_overhead",
            (
                trace(ScenarioMetric.DIRECT_LABOR_COST),
                trace(ScenarioMetric.LABOR_BURDEN_COST),
                trace(ScenarioMetric.DIRECT_MATERIAL_COST),
                trace(ScenarioMetric.OTHER_DIRECT_COST),
                trace(ScenarioMetric.FIXED_OVERHEAD),
                trace(ScenarioMetric.VARIABLE_OVERHEAD),
            ),
        ),
        _value(
            "productive_hours",
            hours,
            "hour",
            "selected productive-hour definition",
            (trace(ScenarioMetric.PRODUCTIVE_HOURS),),
        ),
        _value(
            "effective_labor_cost_per_productive_hour",
            (labor + burden) / hours,
            "USD/hour",
            "(direct_labor + burden) / productive_hours",
            (
                trace(ScenarioMetric.DIRECT_LABOR_COST),
                trace(ScenarioMetric.LABOR_BURDEN_COST),
                trace(ScenarioMetric.PRODUCTIVE_HOURS),
            ),
        ),
        _value(
            "break_even_revenue",
            fixed / contribution_margin,
            "USD",
            "fixed_overhead / contribution_margin",
            break_even_components,
        ),
        _value(
            "break_even_revenue_per_productive_hour",
            (fixed / contribution_margin) / hours,
            "USD/hour",
            "break_even_revenue / productive_hours",
            (*break_even_components, trace(ScenarioMetric.PRODUCTIVE_HOURS)),
        ),
        _value(
            "contribution_amount",
            contribution,
            "USD",
            "revenue - variable_and_direct_cost",
            (*revenue_components, *cost_components),
        ),
        _value(
            "contribution_margin",
            contribution_margin,
            "ratio",
            "contribution / revenue",
            (*revenue_components, *cost_components),
        ),
        _value(
            "gross_margin_result",
            gross / revenue if revenue else Decimal(0),
            "ratio",
            "(revenue - direct_cost) / revenue",
            (
                *revenue_components,
                trace(ScenarioMetric.DIRECT_LABOR_COST),
                trace(ScenarioMetric.LABOR_BURDEN_COST),
                trace(ScenarioMetric.DIRECT_MATERIAL_COST),
                trace(ScenarioMetric.OTHER_DIRECT_COST),
            ),
        ),
        _value(
            "operating_margin_result",
            operating / revenue if revenue else Decimal(0),
            "ratio",
            "(revenue - total_operating_cost) / revenue",
            (
                *revenue_components,
                trace(ScenarioMetric.DIRECT_LABOR_COST),
                trace(ScenarioMetric.LABOR_BURDEN_COST),
                trace(ScenarioMetric.DIRECT_MATERIAL_COST),
                trace(ScenarioMetric.OTHER_DIRECT_COST),
                trace(ScenarioMetric.FIXED_OVERHEAD),
                trace(ScenarioMetric.VARIABLE_OVERHEAD),
            ),
        ),
    )
    return results


def _trace(
    metric: ScenarioMetric,
    measured: dict[ScenarioMetric, MeasuredScenarioFact],
    assumptions: tuple[ScenarioAssumption, ...],
) -> ComponentTrace:
    assumed = next((x for x in assumptions if x.metric is metric), None)
    if assumed:
        return ComponentTrace(
            metric.value,
            assumed.value,
            assumed.unit,
            ValueClass.SCENARIO_ASSUMPTION,
            assumed.provenance,
        )
    fact = measured[metric]
    assert fact.value is not None
    return ComponentTrace(
        metric.value,
        fact.value,
        fact.unit,
        ValueClass.MEASURED_FACT,
        fact.evidence_digest,
    )


def _value(
    name: str,
    value: Decimal,
    unit: str,
    formula: str,
    components: tuple[ComponentTrace, ...],
) -> EconomicCalculationValue:
    return EconomicCalculationValue(name, value, unit, formula, components)


def _required(
    values: dict[ScenarioMetric, Decimal | None], metric: ScenarioMetric
) -> Decimal:
    value = values.get(metric)
    if value is None:
        raise ScenarioCalculationBlocked((f"missing_evidence:{metric.value}",))
    return value


def _overhead_formula(policy: BreakEvenPolicySnapshot) -> str:
    method = next(
        x.value
        for x in policy.selections
        if x.kind is BreakEvenPolicyKind.OVERHEAD_ALLOCATION_METHOD
    )
    return f"fixed_overhead + variable_overhead; allocation_method={method}"


def _scope_blockers(
    policy: BreakEvenPolicySnapshot, service_line: str | None
) -> tuple[str, ...]:
    scope = next(
        (
            x.value
            for x in policy.selections
            if x.kind is BreakEvenPolicyKind.ALLOCATION_SCOPE
        ),
        None,
    )
    service = next(
        (
            x.value
            for x in policy.selections
            if x.kind is BreakEvenPolicyKind.SERVICE_LINE_ALLOCATION
        ),
        None,
    )
    blockers = []
    if policy.branch_id is not None and scope != "branch":
        blockers.append("branch_result_requires_branch_allocation_policy")
    if service_line is not None and service == "none_company_only":
        blockers.append("service_line_result_not_permitted_by_policy")
    return tuple(blockers)


def _deltas(
    baseline: tuple[EconomicCalculationValue, ...],
    scenario: tuple[EconomicCalculationValue, ...],
    facts: tuple[MeasuredScenarioFact, ...],
    assumptions: tuple[ScenarioAssumption, ...],
) -> tuple[ScenarioDelta, ...]:
    base = {x.name: x for x in baseline}
    result = [
        ScenarioDelta(
            x.name, base[x.name].value, x.value, x.value - base[x.name].value, x.unit
        )
        for x in scenario
    ]
    measured = {x.metric: x for x in facts}
    for assumption in assumptions:
        original = measured.get(assumption.metric)
        if original is not None and original.value is not None:
            result.append(
                ScenarioDelta(
                    assumption.metric.value,
                    original.value,
                    assumption.value,
                    assumption.value - original.value,
                    assumption.unit,
                )
            )
    return tuple(sorted(result, key=lambda x: x.metric))


def _policy_refs(policy: BreakEvenPolicySnapshot) -> tuple[tuple[str, str, int], ...]:
    return tuple((x.kind.value, str(x.policy_id), x.version) for x in policy.selections)


def _blocked(
    policy: BreakEvenPolicySnapshot,
    facts: tuple[MeasuredScenarioFact, ...],
    blockers: tuple[str, ...],
    service_line: str | None,
    scenario: ScenarioIdentity | None = None,
) -> GovernedBreakEvenCalculation:
    periods = {(x.period_start, x.period_end) for x in facts}
    start, end = next(iter(periods)) if len(periods) == 1 else (None, None)
    exact = tuple(sorted(set(blockers)))
    body = {
        "contract_version": ENGINE_VERSION,
        "state": CalculationState.BLOCKED,
        "company_id": policy.company_id,
        "branch_id": policy.branch_id,
        "service_line": service_line,
        "period_start": start,
        "period_end": end,
        "evidence_digests": sorted(x.evidence_digest for x in facts),
        "policy_references": _policy_refs(policy),
        "scenario_id": scenario.scenario_id if scenario else None,
        "scenario_version": scenario.version if scenario else None,
        "blockers": exact,
        "scenario_is_measured_actual": False,
        "recommendation": None,
    }
    return GovernedBreakEvenCalculation(
        ENGINE_VERSION,
        CalculationState.BLOCKED,
        policy.company_id,
        policy.branch_id,
        service_line,
        start,
        end,
        tuple(sorted(x.evidence_digest for x in facts)),
        _policy_refs(policy),
        scenario.scenario_id if scenario else None,
        scenario.version if scenario else None,
        (),
        (),
        (),
        exact,
        False,
        None,
        _digest(body),
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
