from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

import pytest
from app.luminary.owner_economics import (
    AnalysisReadiness,
    ScenarioAssumption,
    ScenarioKind,
    project_owner_economics,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def workspace(*, quality: str = "complete") -> dict[str, object]:
    return {
        "period": {"start": "2026-08-01", "end": "2026-08-31"},
        "prior_period": {"start": "2026-07-01", "end": "2026-07-31"},
        "quality_state": quality,
        "currency": "USD",
        "source_result_count": 2,
        "excluded_job_count": 0,
        "unclassified_job_count": 0,
        "fully_allocated_available": False,
        "totals": {
            "revenue": 300_000,
            "labor": 90_000,
            "materials": 80_000,
            "equipment": 10_000,
            "truck": 5_000,
            "gross_profit": 115_000,
            "overhead": None,
        },
        "jobs": [
            {
                "result_id": "result-a",
                "result_digest": "a" * 64,
                "job_id": "job-a",
                "job_number": "J-100",
                "revenue_minor": 100_000,
                "labor_minor": 70_000,
                "materials_minor": 40_000,
                "other_direct_cost_minor": 5_000,
                "contribution_minor": -15_000,
                "confidence_percent": 90,
                "quality_state": quality,
                "missing_categories": [],
            },
            {
                "result_id": "result-b",
                "result_digest": "b" * 64,
                "job_id": "job-b",
                "job_number": "J-200",
                "revenue_minor": 200_000,
                "labor_minor": 20_000,
                "materials_minor": 40_000,
                "other_direct_cost_minor": 10_000,
                "contribution_minor": 130_000,
                "confidence_percent": 95,
                "quality_state": quality,
                "missing_categories": [],
            },
        ],
        "service_categories": [
            {
                "label": "Drain",
                "jobs": 2,
                "complete_jobs": 2,
                "revenue_minor": 300_000,
                "contribution_minor": 115_000,
                "quality_state": quality,
            }
        ],
        "comparison": {
            "state": "available",
            "current": {
                "revenue_minor": 300_000,
                "contribution_minor": 115_000,
                "labor_minor": 90_000,
                "materials_minor": 80_000,
                "other_direct_cost_minor": 15_000,
            },
            "prior": {
                "revenue_minor": 280_000,
                "contribution_minor": 110_000,
                "labor_minor": 82_000,
                "materials_minor": 78_000,
                "other_direct_cost_minor": 10_000,
            },
            "revenue_change_minor": 20_000,
            "contribution_change_minor": 5_000,
            "labor_change_minor": 8_000,
            "materials_change_minor": 2_000,
            "other_direct_cost_change_minor": 5_000,
            "evidence_references": {
                "current": [{"result_id": "result-a", "result_digest": "a" * 64}],
                "prior": [{"result_id": "result-prior", "result_digest": "c" * 64}],
            },
        },
        "readiness": {"allocation_policy": "policy_required"},
    }


def project(
    value: dict[str, object], scenario: ScenarioAssumption | None = None
) -> dict[str, object]:
    return project_owner_economics(
        value,
        company_id=COMPANY,
        branch_id=BRANCH,
        generated_at=NOW,
        scenario=scenario,
    )


def test_fact_projection_is_deterministic_scoped_and_source_labeled() -> None:
    first = project(workspace())
    second = project(deepcopy(workspace()))
    assert first == second
    assert first["packet_digest"] == second["packet_digest"]
    assert first["readiness"] == AnalysisReadiness.READY
    assert first["prior_period"] == {
        "start": "2026-07-01",
        "end": "2026-07-31",
    }
    facts = first["facts"]
    assert isinstance(facts, list)
    revenue = next(item for item in facts if item["metric"] == "revenue")
    assert revenue["value"] == 300_000
    assert revenue["authority"] == "admitted_immutable_actual_results"
    assert revenue["subject"]["company_id"] == str(COMPANY)
    assert revenue["subject"]["branch_id"] == str(BRANCH)
    assert revenue["evidence_references"]


def test_owner_health_uses_only_same_period_admitted_economics() -> None:
    value = workspace()
    value["fully_allocated_available"] = True
    totals = value["totals"]
    assert isinstance(totals, dict)
    totals["overhead"] = 100_000
    result = project(value)["owner_health"]
    assert result["revenue_production"] == {
        "value_minor": 300_000,
        "classification": "MEASURED",
        "basis": "earned_revenue",
        "currency": "USD",
        "limitation": None,
    }
    assert result["economic_contribution"]["value_minor"] == 115_000
    assert result["required_economic_burden"]["classification"] == "AUTHORITATIVE"
    assert result["economic_health"]["value_basis_points"] == 11_500
    assert result["economic_health"]["status"] == "ABOVE_BREAK_EVEN"
    assert result["cash_health"]["separate_from_economic_health"] is True


def test_owner_health_keeps_missing_burden_and_health_unavailable() -> None:
    result = project(workspace())["owner_health"]
    assert result["economic_contribution"]["classification"] == "MEASURED"
    assert result["required_economic_burden"]["value_minor"] is None
    assert (
        "owner_compensation" in result["required_economic_burden"]["missing_components"]
    )
    assert result["economic_health"]["status"] == "UNAVAILABLE"
    assert result["economic_health"]["value_basis_points"] is None


def test_active_reasoning_ranks_decision_dependencies_without_values() -> None:
    result = project(workspace())["active_reasoning"]
    assert result["contribution"] == {
        "state": "AUTHORITATIVE",
        "value_minor": 115_000,
        "job_population_coverage_basis_points": 10_000,
        "coverage_basis": "jobs_with_complete_admitted_variable_costs",
        "ready_job_count": 2,
        "job_count": 2,
    }
    assert result["required_burden"]["state"] == "UNAVAILABLE"
    assert result["economic_health"]["status"] == "UNAVAILABLE"
    assert result["highest_value_next_action"]["gap"] == "field_capacity_burden"
    assert result["highest_value_next_action"]["responsible_party"] == "ACCOUNTANT"
    assert result["highest_value_next_action"]["ui_path"] == "/payroll"
    assert all("value" not in item for item in result["ranked_evidence_gaps"])
    assert "does not prove" in result["cannot_conclude"][-1]


def test_partial_reasoning_prioritizes_gaps_affecting_more_jobs() -> None:
    value = workspace()
    jobs = value["jobs"]
    assert isinstance(jobs, list)
    jobs[0]["contribution_minor"] = None
    jobs[0]["missing_categories"] = ["actual_material_valuation"]
    value["totals"]["gross_profit"] = None
    value["native_evidence"] = {
        "jobs": [
            {
                "job_id": "job-a",
                "job_number": "J-100",
                "job_status": "completed",
                "customer_id": "customer-a",
                "customer_name": "Fixture Customer",
                "branch_id": str(BRANCH),
                "branch_name": "Main",
                "service_category": "drain",
                "invoiced_revenue_minor": 100_000,
                "accepted_worked_seconds": 3_600,
                "material_quantity_evidence_count": 1,
                "material_cost_minor": None,
                "references": [],
            }
        ]
    }
    reasoning = project(value)["active_reasoning"]
    assert reasoning["contribution"]["state"] == "PARTIAL"
    assert reasoning["contribution"]["job_population_coverage_basis_points"] == 5_000
    material = next(
        item
        for item in reasoning["ranked_evidence_gaps"]
        if item["gap"] == "actual_material_valuation"
    )
    assert material["decision_impact"] == "BLOCKS_CONTRIBUTION_AND_HEALTH"
    assert material["expected_source"] == "Inventory / Purchasing / Accounting"
    assert material["unlocks"] == "actual material cost and stronger Job contribution"


def test_complete_health_has_no_fabricated_burden_gap() -> None:
    value = workspace()
    value["fully_allocated_available"] = True
    value["totals"]["overhead"] = 100_000
    reasoning = project(value)["active_reasoning"]
    assert reasoning["economic_health"] == {
        "state": "MEASURED",
        "status": "ABOVE_BREAK_EVEN",
        "value_basis_points": 11_500,
    }
    assert reasoning["ranked_evidence_gaps"] == []
    assert reasoning["highest_value_next_action"] is None


def test_completion_planner_projects_explicit_categories_and_unlock_graph() -> None:
    planner = project(workspace())["economic_completion_planner"]
    assert planner["contract_version"] == "luminary.economic-completion-planner.v1"
    assert planner["read_only"] is True
    assert planner["summary"] == {
        "complete_category_count": 3,
        "partial_category_count": 1,
        "missing_category_count": 8,
        "unavailable_category_count": 0,
        "total_category_count": 12,
    }
    categories = {item["category"]: item for item in planner["categories"]}
    assert categories["FIELD_LABOR_AND_PAYROLL_BURDEN"]["state"] == "PARTIAL"
    assert categories["MATERIAL_AND_JOB_VARIABLE_COST"]["state"] == "COMPLETE"
    assert categories["OWNER_COMPENSATION"]["state"] == "MISSING"
    assert categories["MARKETING_SPEND"]["normal_workflow_available"] is True
    assert categories["MARKETING_SPEND"]["ui_path"] == (
        "/marketing/provider-connections/google-ads"
    )
    assert planner["highest_value_next_completion"]["category"] == (
        "FIELD_LABOR_AND_PAYROLL_BURDEN"
    )
    assert {
        edge["to"]
        for edge in planner["decision_unlock_graph"]["edges"]
        if edge["from"] == "MATERIAL_AND_JOB_VARIABLE_COST"
    } >= {"ECONOMIC_CONTRIBUTION", "ECONOMIC_HEALTH"}


def test_completion_planner_does_not_invent_owner_confirmed_value_authority() -> None:
    planner = project(workspace())["economic_completion_planner"]
    assert planner["owner_confirmed_authority"]["found"] is False
    assert (
        "effective-dated"
        in planner["owner_confirmed_authority"]["required_future_contract"]
    )
    for category in planner["categories"]:
        assert category["owner_confirmed"]["supported"] is False
        assert category["owner_confirmed"]["effective_period"] == {
            "start": "2026-08-01",
            "end": "2026-08-31",
        }
        assert "value" not in category["owner_confirmed"]


def test_owner_action_map_preserves_source_authority_and_dependency_order() -> None:
    action_map = project(workspace())["economic_completion_planner"]["owner_action_map"]
    actions = {item["action"]: item for item in action_map["actions"]}
    evaluations = {item["action"]: item for item in action_map["evaluations"]}

    assert action_map["top_action"]["action"] == ("COMPLETE_PAYROLL_ECONOMIC_EVIDENCE")
    assert actions["COMPLETE_PAYROLL_ECONOMIC_EVIDENCE"]["ui_path"] == "/payroll"
    assert actions["COMPLETE_PAYROLL_ECONOMIC_EVIDENCE"]["responsible_parties"] == [
        "OWNER",
        "EMPLOYEE",
        "ACCOUNTANT",
        "SYSTEM",
    ]
    material = evaluations["COMPLETE_JOB_MATERIAL_COST_EVIDENCE"]
    assert material["evidence_chain"] == {
        "material_catalog": "SEPARATE_AUTHORITY_NOT_PROOF_OF_JOB_COST",
        "job_material_attribution": "PARTIAL",
        "actual_job_cost": "AVAILABLE",
    }
    accounting = actions["RECONCILE_ACCOUNTING_EVIDENCE"]
    assert accounting["ui_path"] == "/accounting/quickbooks-migration"
    assert accounting["evidence_chain"]["qbo_workspace"] == (
        "SOURCE_ACQUISITION_AND_APPLICATION_READINESS_ONLY"
    )
    assert accounting["evidence_chain"]["reconciled_accounting"] == "PARTIAL"
    marketing = actions["ADMIT_MARKETING_SPEND_EVIDENCE"]
    assert marketing["ui_path"] == "/marketing/provider-connections/google-ads"
    assert marketing["source_state"] == "NOT_ADMITTED_TO_ECONOMICS"
    assert all(item["sequence_bucket"] == "NOW" for item in action_map["actions"])
    assert "not invented urgency" in action_map["limitations"][0]


def test_owner_action_map_removes_completed_categories_without_faking_qbo_completion() -> (
    None
):
    value = workspace()
    value["fully_allocated_available"] = True
    value["totals"]["overhead"] = 100_000
    action_map = project(value)["economic_completion_planner"]["owner_action_map"]
    action_keys = {item["action"] for item in action_map["actions"]}

    assert "COMPLETE_PAYROLL_ECONOMIC_EVIDENCE" not in action_keys
    assert "COMPLETE_FIXED_BURDEN_AUTHORITY" not in action_keys
    assert "RECONCILE_ACCOUNTING_EVIDENCE" in action_keys
    assert action_map["top_action"]["action"] == "RECONCILE_ACCOUNTING_EVIDENCE"


def test_completion_planner_does_not_call_absent_job_evidence_complete() -> None:
    value = workspace(quality="unavailable")
    value["jobs"] = []
    value["service_categories"] = []
    value["source_result_count"] = 0
    value["totals"] = {
        "revenue": None,
        "labor": None,
        "materials": None,
        "equipment": None,
        "truck": None,
        "gross_profit": None,
        "overhead": None,
    }

    planner = project(value)["economic_completion_planner"]
    categories = {item["category"]: item for item in planner["categories"]}

    assert categories["MATERIAL_AND_JOB_VARIABLE_COST"]["state"] == "UNAVAILABLE"
    assert categories["MERCHANT_FEES"]["state"] == "UNAVAILABLE"
    assert (
        categories["PERMITS_SUBCONTRACTORS_DISPOSAL_AND_RENTALS"]["state"]
        == "UNAVAILABLE"
    )
    assert planner["summary"]["unavailable_category_count"] == 3
    assert planner["summary"]["complete_category_count"] == 0
    assert all(
        item["category"] != "MATERIAL_AND_JOB_VARIABLE_COST"
        for item in planner["ranked_completion_plan"]
    )


def test_completion_plan_uses_authoritative_population_not_missing_value() -> None:
    value = workspace()
    jobs = value["jobs"]
    assert isinstance(jobs, list)
    jobs[0]["contribution_minor"] = None
    jobs[0]["missing_categories"] = ["actual_material_valuation"]
    value["totals"]["gross_profit"] = None
    value["native_evidence"] = {
        "jobs": [
            {
                "job_id": "job-a",
                "job_number": "J-100",
                "job_status": "completed",
                "customer_id": "customer-a",
                "customer_name": "Fixture Customer",
                "branch_id": str(BRANCH),
                "branch_name": "Main",
                "service_category": "drain",
                "invoiced_revenue_minor": 100_000,
                "accepted_worked_seconds": 3_600,
                "material_quantity_evidence_count": 1,
                "material_cost_minor": None,
                "references": [],
            }
        ]
    }
    planner = project(value)["economic_completion_planner"]
    material = next(
        item
        for item in planner["ranked_completion_plan"]
        if item["category"] == "MATERIAL_AND_JOB_VARIABLE_COST"
    )
    assert material["affected_job_count"] == 1
    assert material["affected_authoritative_revenue_minor"] == 100_000
    assert "estimated_missing_value_minor" not in material
    assert planner["ranking_limit"] == (
        "No missing dollar value or industry estimate is used."
    )


def test_driver_analysis_quantifies_materiality_without_claiming_cause() -> None:
    drivers = project(workspace())["driver_analysis"]
    assert drivers["state"] == "AVAILABLE"
    observations = {item["metric"]: item for item in drivers["observed_changes"]}
    assert observations["revenue_production"]["change"] == 20_000
    assert observations["revenue_production"]["change_basis_points_of_prior"] == 714
    assert observations["economic_contribution"]["change"] == 5_000
    assert observations["job_variable_cost"]["change"] == 15_000
    assert observations["material_cost_per_job"]["change"] == 2_000
    assert observations["job_count"]["current"] == 1
    measured = drivers["measured_drivers"]
    assert measured[0] == {
        "component": "revenue_production",
        "classification": "MEASURED_DRIVER",
        "contribution_effect_minor": 20_000,
        "materiality_basis": "absolute_arithmetic_contribution_effect",
        "causality": "UNPROVEN",
    }
    assert drivers["unproven_causes"][0]["classification"] == "UNPROVEN_CAUSE"
    assert drivers["cash_health"]["ar_and_collections_included"] is False


def test_driver_analysis_fails_closed_without_comparable_periods() -> None:
    value = workspace()
    value["comparison"] = {
        "state": "unavailable",
        "reason": "Prior equal-period evidence is incomplete.",
    }
    drivers = project(value)["driver_analysis"]
    assert drivers["state"] == "UNAVAILABLE"
    assert drivers["reason"] == "Prior equal-period evidence is incomplete."
    assert drivers["observed_changes"] == []
    assert drivers["measured_drivers"] == []


def test_gap_ranking_uses_authoritative_population_value_not_missing_value() -> None:
    value = workspace()
    value["native_evidence"] = {
        "jobs": [
            {
                "job_id": "job-a",
                "job_number": "J-100",
                "job_status": "completed",
                "customer_id": "customer-a",
                "customer_name": "Fixture Customer",
                "branch_id": str(BRANCH),
                "branch_name": "Main",
                "service_category": "drain",
                "invoiced_revenue_minor": 100_000,
                "accepted_worked_seconds": 3_600,
                "material_quantity_evidence_count": 1,
                "material_cost_minor": None,
                "references": [],
            }
        ]
    }
    reasoning = project(value)["active_reasoning"]
    material = next(
        item
        for item in reasoning["ranked_evidence_gaps"]
        if item["gap"] == "actual_material_valuation"
    )
    assert material["affected_authoritative_revenue_minor"] == 100_000
    assert "estimated_missing_value_minor" not in material
    assert material["normal_workflow_available"] is True
    assert material["evidence_freshness"] == "complete"


def test_equal_period_delta_is_exactly_decomposed_without_causal_claim() -> None:
    delta = project(workspace())["delta_explanation"]
    assert delta["state"] == "EXPLAINED"
    assert delta["classification"] == "DETERMINISTIC_DERIVED_CALCULATION"
    assert delta["contribution_change_minor"] == 5_000
    assert delta["explained_change_minor"] == 5_000
    assert delta["unexplained_change_minor"] == 0
    assert delta["contribution_margin_change_basis_points"] == -95
    assert delta["scope"] == {
        "company_id": str(COMPANY),
        "branch_id": str(BRANCH),
    }
    assert delta["evidence_references"]["prior"][0]["result_id"] == "result-prior"
    assert "not operational cause" in delta["causality_boundary"]


def test_zero_delta_remains_a_deterministic_explanation() -> None:
    value = workspace()
    comparison = value["comparison"]
    assert isinstance(comparison, dict)
    for key in (
        "revenue_change_minor",
        "contribution_change_minor",
        "labor_change_minor",
        "materials_change_minor",
        "other_direct_cost_change_minor",
    ):
        comparison[key] = 0
    comparison["prior"] = deepcopy(comparison["current"])
    delta = project(value)["delta_explanation"]
    assert delta["state"] == "EXPLAINED"
    assert delta["contribution_change_minor"] == 0
    assert delta["unexplained_change_minor"] == 0
    assert "did not change" in delta["headline"]


def test_incomplete_or_conflicting_comparison_fails_closed() -> None:
    incomplete = workspace()
    comparison = incomplete["comparison"]
    assert isinstance(comparison, dict)
    comparison.pop("other_direct_cost_change_minor")
    delta = project(incomplete)["delta_explanation"]
    assert delta["state"] == "INCOMPLETE"
    assert delta["components"] == []

    conflicting = workspace(quality="conflicting")
    conflicting["comparison"] = {
        "state": "unavailable",
        "reason": "Both periods require one non-conflicting authority.",
    }
    delta = project(conflicting)["delta_explanation"]
    assert delta["state"] == "CONFLICTING"
    assert "non-conflicting" in delta["reason"]


def test_stale_or_missing_prior_evidence_is_not_comparable() -> None:
    stale = workspace(quality="stale")
    stale["comparison"] = {
        "state": "unavailable",
        "reason": "Both comparable periods require current admitted evidence.",
    }
    delta = project(stale)["delta_explanation"]
    assert delta["state"] == "NOT_COMPARABLE"
    assert delta["freshness"] == "stale"

    missing_prior = workspace()
    missing_prior["prior_period"] = None
    missing_prior["comparison"] = {
        "state": "unavailable",
        "reason": "A prior equal-length period is unavailable.",
    }
    delta = project(missing_prior)["delta_explanation"]
    assert delta["state"] == "NOT_COMPARABLE"
    assert delta["prior_period"] is None


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        ("partial", AnalysisReadiness.PARTIAL),
        ("conflicting", AnalysisReadiness.CONFLICTING_EVIDENCE),
        ("unavailable", AnalysisReadiness.SOURCE_MISSING),
    ],
)
def test_incomplete_evidence_is_explicit_and_suppresses_recommendations(
    quality: str, expected: AnalysisReadiness
) -> None:
    result = project(workspace(quality=quality))
    assert result["readiness"] == expected
    assert result["recommendation_candidates"] == []


def test_negative_contribution_creates_review_candidate_not_price_activation() -> None:
    result = project(workspace())
    candidates = result["recommendation_candidates"]
    assert isinstance(candidates, list) and len(candidates) == 1
    candidate = candidates[0]
    assert candidate["family"] == "PRICING"
    assert candidate["status"] == "CANDIDATE_READ_ONLY"
    assert candidate["estimated_range"] is None
    assert any(
        "does not establish underpricing" in item for item in candidate["uncertainty"]
    )
    assert result["mutation_authority"] == "none"
    assert not any(key in result for key in ("command", "activation", "posting"))


def test_single_scenario_changes_only_selected_input_and_preserves_baseline() -> None:
    baseline = workspace()
    original = deepcopy(baseline)
    result = project(
        baseline,
        ScenarioAssumption(ScenarioKind.LABOR_EFFICIENCY_PERCENT, 1_000),
    )
    scenario = result["scenario"]
    assert scenario["hypothetical"] is True
    assert scenario["authoritative_actual"] is False
    assert scenario["baseline"]["labor"] == 90_000
    assert scenario["output_metrics"]["labor"] == 81_000
    assert scenario["output_metrics"]["revenue"] == 300_000
    assert scenario["operational_action_occurred"] is False
    assert baseline == original


@pytest.mark.parametrize(
    "kind", [ScenarioKind.CLOSE_RATE_PERCENT, ScenarioKind.ADD_TRUCK]
)
def test_unsupported_scenario_returns_exact_evidence_blocker(
    kind: ScenarioKind,
) -> None:
    scenario = project(workspace(), ScenarioAssumption(kind))["scenario"]
    assert scenario["state"] == AnalysisReadiness.INSUFFICIENT_EVIDENCE
    assert scenario["missing_prerequisites"]
    assert scenario["operational_action_occurred"] is False


def test_workforce_market_beacon_and_lia_boundaries_are_non_mutating() -> None:
    result = project(workspace())
    assert result["market_evidence"]["state"] == "INSUFFICIENT_MARKET_EVIDENCE"
    assert "no ranking" in result["workforce_boundary"]
    assert "retains lifecycle ownership" in result["beacon_boundary"]
    assert "LIA may present" in result["lia_boundary"]
    assert all(
        "termination" not in str(candidate).lower()
        for candidate in result["recommendation_candidates"]
    )


def test_scenario_validation_rejects_silent_compounding() -> None:
    with pytest.raises(ValueError, match="cannot imply"):
        ScenarioAssumption(ScenarioKind.ADD_TRUCK, 1_000)
    with pytest.raises(ValueError, match="between"):
        ScenarioAssumption(ScenarioKind.PRICE_PERCENT, 10_001)


def test_native_evidence_produces_partial_confident_facts_without_margin() -> None:
    value = {
        "period": {"start": "2026-09-01", "end": "2026-09-30"},
        "quality_state": "unavailable",
        "totals": None,
        "jobs": [],
        "fully_allocated_available": False,
        "comparison": {"state": "unavailable"},
        "native_evidence_comparison": {
            "state": "AVAILABLE",
            "basis": "ACP_NATIVE_INVOICED",
            "invoiced_revenue_change_minor": 2_500,
        },
        "native_evidence": {
            "admitted_reference_count": 2,
            "families": {
                "REVENUE": {"state": "AVAILABLE"},
                "DIRECT_LABOR": {"state": "PARTIAL"},
            },
            "summary": {
                "invoiced_revenue_minor": 12_500,
                "currency": "USD",
                "accepted_worked_seconds": 3_600,
            },
            "jobs": [
                {
                    "job_id": "job-native-1",
                    "job_number": "J-NATIVE-1",
                    "job_status": "completed",
                    "customer_id": "customer-1",
                    "customer_name": "All County Customer",
                    "branch_id": str(BRANCH),
                    "branch_name": "Main",
                    "service_category": "drain_cleaning",
                    "invoiced_revenue_minor": 12_500,
                    "settlement_applied_minor": None,
                    "accepted_worked_seconds": 3_600,
                    "material_quantity_evidence_count": 1,
                    "material_cost_minor": None,
                    "references": [
                        {
                            "family": "REVENUE",
                            "record_id": "invoice-1",
                            "digest": "a" * 64,
                        },
                        {
                            "family": "DIRECT_LABOR",
                            "record_id": "interval-1",
                            "digest": "b" * 64,
                        },
                    ],
                }
            ],
        },
        "readiness": {"allocation_policy": "policy_required"},
    }
    result = project(value)
    assert result["readiness"] == AnalysisReadiness.PARTIAL
    assert result["confidence"]["score_percent"] == 70
    invoiced = next(
        item for item in result["facts"] if item["metric"] == "invoiced_revenue"
    )
    worked = next(
        item for item in result["facts"] if item["metric"] == "accepted_worked_seconds"
    )
    margin = next(item for item in result["facts"] if item["metric"] == "gross_profit")
    assert invoiced["value"] == 12_500
    assert invoiced["authority"] == "accepted_native_invoiced_or_valued_fact"
    assert worked["value"] == 3_600
    assert margin["value"] is None
    jobs = result["job_economics"]
    assert jobs[0]["job_number"] == "J-NATIVE-1"
    assert jobs[0]["readiness"] == "PARTIAL"
    assert jobs[0]["invoiced_revenue_minor"] == 12_500
    assert jobs[0]["direct_wage_cost_minor"] is None
    assert "certified_direct_wage_cost" in jobs[0]["missing_prerequisites"]
    assert jobs[0]["evidence_states"]["direct_wage_cost"] == "POLICY_REQUIRED"
    service = result["service_line_economics"][0]
    assert service["service_category"] == "drain_cleaning"
    delta = result["delta_explanation"]
    assert delta["state"] == "PARTIAL"
    assert delta["classification"] == "MEASURED_PERIOD_DIFFERENCE"
    assert delta["components"][0]["component"] == "invoiced_revenue"
    assert "admitted_direct_contribution" in delta["missing_evidence"]
    assert service["invoiced_revenue_minor"] == 12_500
    assert service["direct_contribution_minor"] is None
    queue = result["evidence_priority_queue"]
    assert queue
    wage = next(
        item for item in queue if item["prerequisite"] == "certified_direct_wage_cost"
    )
    assert wage["affected_job_count"] == 1
    assert wage["responsible_domain"] == "Payroll/Economics policy"
    answers = result["owner_question_answers"]
    assert answers["which_jobs_make_money"]["state"] == "INSUFFICIENT_EVIDENCE"
    assert answers["what_prevents_fully_loaded_profit"]["state"] == "POLICY_REQUIRED"
    assert result["trend_support"]["state"] == "READY"
    assert result["recommendation_candidates"] == []
