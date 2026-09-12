import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.business_economics.break_even_calculation import (
    CalculationState,
    ScenarioIdentity,
    calculate_governed_break_even,
)
from app.business_economics.break_even_explanation import (
    OwnerDecisionState,
    build_owner_policy_selection_packet,
    explain_break_even_calculation,
)
from app.business_economics.break_even_policy import (
    BreakEvenPolicyKind,
    PolicyApprovalState,
    PolicyApproverRole,
    build_break_even_policy_snapshot,
    seal_break_even_policy,
)
from app.business_economics.break_even_scenario import (
    MeasuredScenarioFact,
    ScenarioAssumption,
    ScenarioMetric,
)

START, END = date(2026, 9, 1), date(2026, 9, 30)
VALUES: dict[BreakEvenPolicyKind, str | Decimal] = {
    BreakEvenPolicyKind.PRODUCTIVE_HOUR_DEFINITION: "accepted_productive_job_time",
    BreakEvenPolicyKind.LABOR_BURDEN_METHOD: "actual_components",
    BreakEvenPolicyKind.OVERHEAD_ALLOCATION_METHOD: "productive_hours",
    BreakEvenPolicyKind.ALLOCATION_SCOPE: "company",
    BreakEvenPolicyKind.OVERHEAD_CLASSIFICATION: "accepted_account_classification",
    BreakEvenPolicyKind.OWNER_COMPENSATION_TREATMENT: "fixed_overhead",
    BreakEvenPolicyKind.VEHICLE_EQUIPMENT_COST_TREATMENT: "direct_attributable",
    BreakEvenPolicyKind.MATERIAL_COSTING_BASIS: "inventory_issue_layer",
    BreakEvenPolicyKind.LABOR_CLASSIFICATION: "job_attributable_direct",
    BreakEvenPolicyKind.CALLBACK_REWORK_TREATMENT: "separate_analysis",
    BreakEvenPolicyKind.MARKETING_ALLOCATION: "fixed_overhead",
    BreakEvenPolicyKind.TARGET_GROSS_MARGIN: Decimal("0.40"),
    BreakEvenPolicyKind.TARGET_OPERATING_MARGIN: Decimal("0.15"),
    BreakEvenPolicyKind.CAPACITY_BUFFER: Decimal("0.10"),
    BreakEvenPolicyKind.UNPRODUCTIVE_TIME_TREATMENT: "separate_capacity",
    BreakEvenPolicyKind.OVERTIME_PREMIUM_TREATMENT: "labor_burden",
    BreakEvenPolicyKind.SERVICE_LINE_ALLOCATION: "none_company_only",
    BreakEvenPolicyKind.ROUNDING_RULE: "no_intermediate_rounding",
}


def _selection(company: UUID, kind: BreakEvenPolicyKind, version: int = 1):
    return seal_break_even_policy(
        policy_id=uuid4(),
        company_id=company,
        branch_id=None,
        kind=kind,
        version=version,
        value=VALUES[kind],
        effective_start=START,
        effective_end=None,
        approval_state=PolicyApprovalState.APPROVED,
        approved_by_user_id=uuid4(),
        approver_role=PolicyApproverRole.OWNER,
        approved_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        provenance="synthetic_owner_decision",
        provenance_digest="a" * 64,
        rationale_notes="qualification only",
        supersedes_policy_id=None,
    )


def _policy(company: UUID, version: int = 1, omit: BreakEvenPolicyKind | None = None):
    return build_break_even_policy_snapshot(
        tuple(
            _selection(company, kind, version)
            for kind in BreakEvenPolicyKind
            if kind is not omit
        ),
        company_id=company,
        branch_id=None,
        as_of=START,
    )


def _facts(company: UUID):
    values = {
        ScenarioMetric.PRODUCTIVE_HOURS: Decimal(100),
        ScenarioMetric.EARNED_REVENUE: Decimal(30000),
        ScenarioMetric.DIRECT_LABOR_COST: Decimal(8000),
        ScenarioMetric.LABOR_BURDEN_COST: Decimal(2000),
        ScenarioMetric.DIRECT_MATERIAL_COST: Decimal(5000),
        ScenarioMetric.OTHER_DIRECT_COST: Decimal(1000),
        ScenarioMetric.FIXED_OVERHEAD: Decimal(7000),
        ScenarioMetric.VARIABLE_OVERHEAD: Decimal(1000),
    }
    return tuple(
        MeasuredScenarioFact(
            metric,
            value,
            "hour" if metric is ScenarioMetric.PRODUCTIVE_HOURS else "USD",
            company,
            None,
            START,
            END,
            "accepted_measurement",
            hashlib.sha256(str(index).encode()).hexdigest(),
        )
        for index, (metric, value) in enumerate(values.items())
    )


def test_deterministic_replay_lineage_and_exact_component_reconciliation() -> None:
    company = uuid4()
    first = calculate_governed_break_even(
        policy=_policy(company), measured_facts=_facts(company)
    )
    second = calculate_governed_break_even(
        policy=_policy(company), measured_facts=_facts(company)
    )
    # Distinct synthetic policy identities differ; replaying the exact snapshot is stable.
    policy_snapshot = _policy(company)
    replay = calculate_governed_break_even(
        policy=policy_snapshot, measured_facts=_facts(company)
    )
    replay_again = calculate_governed_break_even(
        policy=policy_snapshot, measured_facts=_facts(company)
    )
    assert replay == replay_again
    assert replay.calculation_digest == replay_again.calculation_digest
    assert first.state is CalculationState.AVAILABLE
    total = next(x for x in first.baseline_results if x.name == "total_operating_cost")
    assert total.value == Decimal(24000)
    assert sum(x.value for x in total.components) == total.value
    assert len(first.measurement_evidence_digests) == 8
    assert len(first.policy_references) == len(BreakEvenPolicyKind)
    assert first.recommendation is None
    assert second.calculation_digest != first.calculation_digest


def test_policy_version_and_scenario_delta_are_explicit_baseline_is_unchanged() -> None:
    company, facts = uuid4(), None
    facts = _facts(company)
    version_one = calculate_governed_break_even(
        policy=_policy(company, 1), measured_facts=facts
    )
    version_two = calculate_governed_break_even(
        policy=_policy(company, 2), measured_facts=facts
    )
    assert version_one.calculation_digest != version_two.calculation_digest
    scenario_policy = _policy(company)
    scenario = calculate_governed_break_even(
        policy=scenario_policy,
        measured_facts=facts,
        scenario=ScenarioIdentity(uuid4(), 1, "productive hours improve"),
        assumptions=(
            ScenarioAssumption(
                ScenarioMetric.PRODUCTIVE_HOURS,
                Decimal(125),
                "hour",
                "scenario only",
                "owner_workspace",
            ),
        ),
    )
    baseline = {x.name: x.value for x in scenario.baseline_results}
    baseline_only = calculate_governed_break_even(
        policy=scenario_policy, measured_facts=facts
    )
    assert baseline == {x.name: x.value for x in baseline_only.baseline_results}
    assert scenario.scenario_is_measured_actual is False
    assert (
        next(
            x for x in scenario.scenario_deltas if x.metric == "productive_hours"
        ).delta
        == 25
    )


def test_missing_conflicting_zero_and_explanations_are_truthful() -> None:
    company = uuid4()
    blocked = calculate_governed_break_even(
        policy=_policy(company, omit=BreakEvenPolicyKind.LABOR_BURDEN_METHOD),
        measured_facts=_facts(company),
    )
    assert blocked.state is CalculationState.BLOCKED
    assert "missing_policy:labor_burden_method" in blocked.blockers
    explanation = explain_break_even_calculation(blocked)
    assert explanation.blocked_because == blocked.blockers
    assert any(
        "labor_burden_method" in x for x in explanation.availability_requirements
    )
    missing = list(_facts(company))
    object.__setattr__(missing[2], "value", None)
    result = calculate_governed_break_even(
        policy=_policy(company), measured_facts=tuple(missing)
    )
    assert "missing_evidence:direct_labor_cost" in result.blockers
    conflict = list(_facts(company))
    object.__setattr__(conflict[2], "conflicting", True)
    result = calculate_governed_break_even(
        policy=_policy(company), measured_facts=tuple(conflict)
    )
    assert "conflicting_evidence:direct_labor_cost" in result.blockers
    zero = list(_facts(company))
    object.__setattr__(zero[4], "value", Decimal(0))
    assert (
        calculate_governed_break_even(
            policy=_policy(company), measured_facts=tuple(zero)
        ).state
        is CalculationState.AVAILABLE
    )


def test_foreign_scope_mixed_period_and_unsupported_service_line_rejected() -> None:
    company = uuid4()
    foreign = list(_facts(company))
    object.__setattr__(foreign[0], "company_id", uuid4())
    with pytest.raises(ValueError, match="foreign Company/Branch"):
        calculate_governed_break_even(
            policy=_policy(company), measured_facts=tuple(foreign)
        )
    mixed = list(_facts(company))
    object.__setattr__(mixed[0], "period_end", date(2026, 10, 1))
    with pytest.raises(ValueError, match="mixed calculation evidence periods"):
        calculate_governed_break_even(
            policy=_policy(company), measured_facts=tuple(mixed)
        )
    blocked = calculate_governed_break_even(
        policy=_policy(company), measured_facts=_facts(company), service_line="plumbing"
    )
    assert blocked.blockers == ("service_line_result_not_permitted_by_policy",)


def test_owner_packet_lists_each_unselected_decision_without_preference() -> None:
    company = uuid4()
    packet = build_owner_policy_selection_packet(
        _policy(company, omit=BreakEvenPolicyKind.OVERHEAD_ALLOCATION_METHOD)
    )
    decision = next(
        x
        for x in packet.decisions
        if x.policy_family is BreakEvenPolicyKind.OVERHEAD_ALLOCATION_METHOD
    )
    assert decision.current_state is OwnerDecisionState.UNSELECTED
    assert decision.supported_options
    assert (
        BreakEvenPolicyKind.OVERHEAD_ALLOCATION_METHOD
        in packet.owner_selection_required
    )
    assert packet.recommendation is None
