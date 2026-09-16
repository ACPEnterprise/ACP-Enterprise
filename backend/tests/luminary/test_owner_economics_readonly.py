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
            "revenue_change_minor": 20_000,
            "contribution_change_minor": -10_000,
            "labor_change_minor": 8_000,
            "materials_change_minor": 2_000,
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
