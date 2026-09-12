import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
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
    ScenarioCalculationBlocked,
    ScenarioMetric,
    evaluate_break_even_scenario,
)

AS_OF = date(2026, 9, 1)
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
    BreakEvenPolicyKind.ROUNDING_RULE: "currency_half_even",
}


def _selection(company: UUID, kind: BreakEvenPolicyKind, *, version: int = 1):
    return seal_break_even_policy(
        policy_id=uuid4(),
        company_id=company,
        branch_id=None,
        kind=kind,
        version=version,
        value=VALUES[kind],
        effective_start=AS_OF,
        effective_end=None,
        approval_state=PolicyApprovalState.APPROVED,
        approved_by_user_id=uuid4(),
        approver_role=PolicyApproverRole.OWNER,
        approved_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        provenance="owner_decision_record",
        provenance_digest="a" * 64,
        rationale_notes="Synthetic approved policy for deterministic qualification.",
        supersedes_policy_id=None,
    )


def _policy(company: UUID, *, version: int = 1):
    return build_break_even_policy_snapshot(
        tuple(
            _selection(company, kind, version=version) for kind in BreakEvenPolicyKind
        ),
        company_id=company,
        branch_id=None,
        as_of=AS_OF,
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
            AS_OF,
            date(2026, 9, 30),
            "accepted_measurement",
            hashlib.sha256(str(index).encode()).hexdigest(),
        )
        for index, (metric, value) in enumerate(values.items())
    )


def test_identical_inputs_are_deterministic_and_classes_are_separate() -> None:
    company = uuid4()
    policy, facts = _policy(company), _facts(company)
    assumption = ScenarioAssumption(
        ScenarioMetric.PRODUCTIVE_HOURS,
        Decimal(110),
        "hour",
        "scenario only",
        "owner_workspace",
    )
    first = evaluate_break_even_scenario(
        policy=policy, measured_facts=facts, assumptions=(assumption,)
    )
    second = evaluate_break_even_scenario(
        policy=policy, measured_facts=facts, assumptions=(assumption,)
    )
    assert first == second
    assert first.result_digest == second.result_digest
    assert first.measured_facts == facts
    assert first.scenario_assumptions == (assumption,)
    assert first.policy_inputs
    assert first.calculated_results
    assert first.recommendation is None
    assert first.mutation_authority == "none"


def test_policy_version_is_explicit_in_changed_result_identity() -> None:
    company, facts = uuid4(), None
    facts = _facts(company)
    first = evaluate_break_even_scenario(
        policy=_policy(company, version=1), measured_facts=facts
    )
    second = evaluate_break_even_scenario(
        policy=_policy(company, version=2), measured_facts=facts
    )
    assert first.result_digest != second.result_digest
    assert {item[2] for item in first.policy_inputs} == {1}
    assert {item[2] for item in second.policy_inputs} == {2}


def test_missing_policy_evidence_and_conflict_block_calculation() -> None:
    company = uuid4()
    selections = tuple(
        _selection(company, kind)
        for kind in BreakEvenPolicyKind
        if kind is not BreakEvenPolicyKind.CAPACITY_BUFFER
    )
    incomplete = build_break_even_policy_snapshot(
        selections, company_id=company, branch_id=None, as_of=AS_OF
    )
    with pytest.raises(
        ScenarioCalculationBlocked, match="missing_policy:capacity_buffer"
    ):
        evaluate_break_even_scenario(policy=incomplete, measured_facts=_facts(company))
    facts = list(_facts(company))
    object.__setattr__(facts[0], "conflicting", True)
    with pytest.raises(
        ScenarioCalculationBlocked, match="conflicting_evidence:productive_hours"
    ):
        evaluate_break_even_scenario(
            policy=_policy(company), measured_facts=tuple(facts)
        )


def test_foreign_scope_mixed_period_and_missing_vs_zero_fail_closed() -> None:
    company = uuid4()
    facts = list(_facts(company))
    object.__setattr__(facts[0], "company_id", uuid4())
    with pytest.raises(ValueError, match="foreign Company/Branch"):
        evaluate_break_even_scenario(
            policy=_policy(company), measured_facts=tuple(facts)
        )
    facts = list(_facts(company))
    object.__setattr__(facts[0], "period_end", date(2026, 10, 1))
    with pytest.raises(ValueError, match="mixed measured periods"):
        evaluate_break_even_scenario(
            policy=_policy(company), measured_facts=tuple(facts)
        )
    facts = list(_facts(company))
    object.__setattr__(facts[1], "value", None)
    with pytest.raises(
        ScenarioCalculationBlocked, match="missing_evidence:earned_revenue"
    ):
        evaluate_break_even_scenario(
            policy=_policy(company), measured_facts=tuple(facts)
        )
    facts = list(_facts(company))
    object.__setattr__(facts[4], "value", Decimal(0))
    result = evaluate_break_even_scenario(
        policy=_policy(company), measured_facts=tuple(facts)
    )
    assert (
        next(
            x
            for x in result.measured_facts
            if x.metric is ScenarioMetric.DIRECT_MATERIAL_COST
        ).value
        == 0
    )


def test_unselected_policy_cannot_masquerade_as_approval() -> None:
    company = uuid4()
    with pytest.raises(ValueError, match="unselected policy"):
        seal_break_even_policy(
            policy_id=uuid4(),
            company_id=company,
            branch_id=None,
            kind=BreakEvenPolicyKind.CAPACITY_BUFFER,
            version=1,
            value=Decimal("0.1"),
            effective_start=AS_OF,
            effective_end=None,
            approval_state=PolicyApprovalState.UNSELECTED,
            approved_by_user_id=None,
            approver_role=None,
            approved_at=None,
            provenance="gap",
            provenance_digest="a" * 64,
            rationale_notes="missing",
            supersedes_policy_id=None,
        )


def test_average_ticket_and_close_rate_require_explicit_opportunity_evidence() -> None:
    company = uuid4()
    assumptions = (
        ScenarioAssumption(
            ScenarioMetric.AVERAGE_TICKET,
            Decimal(600),
            "USD",
            "scenario only",
            "owner_workspace",
        ),
        ScenarioAssumption(
            ScenarioMetric.CLOSE_RATE,
            Decimal("0.50"),
            "ratio",
            "scenario only",
            "owner_workspace",
        ),
    )
    with pytest.raises(
        ScenarioCalculationBlocked,
        match="revenue_scenario_requires:opportunity_count",
    ):
        evaluate_break_even_scenario(
            policy=_policy(company),
            measured_facts=_facts(company),
            assumptions=assumptions,
        )
    opportunity = MeasuredScenarioFact(
        ScenarioMetric.OPPORTUNITY_COUNT,
        Decimal(100),
        "count",
        company,
        None,
        AS_OF,
        date(2026, 9, 30),
        "accepted_comparable_opportunities",
        hashlib.sha256(b"opportunities").hexdigest(),
    )
    result = evaluate_break_even_scenario(
        policy=_policy(company),
        measured_facts=(*_facts(company), opportunity),
        assumptions=assumptions,
    )
    contribution = next(
        item
        for item in result.calculated_results
        if item.metric == "measured_contribution"
    )
    assert contribution.value == Decimal("13000.00")


def test_explicit_successor_shadows_prior_policy_without_rewriting_history() -> None:
    company = uuid4()
    original = _selection(company, BreakEvenPolicyKind.CAPACITY_BUFFER)
    successor = seal_break_even_policy(
        policy_id=uuid4(),
        company_id=company,
        branch_id=None,
        kind=BreakEvenPolicyKind.CAPACITY_BUFFER,
        version=2,
        value=Decimal("0.20"),
        effective_start=AS_OF,
        effective_end=None,
        approval_state=PolicyApprovalState.APPROVED,
        approved_by_user_id=uuid4(),
        approver_role=PolicyApproverRole.ACCOUNTANT,
        approved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        provenance="accountant_decision_record",
        provenance_digest="b" * 64,
        rationale_notes="Synthetic successor qualification.",
        supersedes_policy_id=original.policy_id,
    )
    other = tuple(
        _selection(company, kind)
        for kind in BreakEvenPolicyKind
        if kind is not BreakEvenPolicyKind.CAPACITY_BUFFER
    )
    snapshot = build_break_even_policy_snapshot(
        (*other, original, successor),
        company_id=company,
        branch_id=None,
        as_of=AS_OF,
    )
    capacity = next(
        item
        for item in snapshot.selections
        if item.kind is BreakEvenPolicyKind.CAPACITY_BUFFER
    )
    assert capacity.version == 2
    assert original.policy_digest != successor.policy_digest
