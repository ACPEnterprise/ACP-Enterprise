from typing import Any

from app.business_economics.owner_intelligence import (
    MAX_CONTEXT_ITEMS,
    OwnerIntelligenceService,
    OwnerQuestion,
)


def projection() -> dict[str, Any]:
    return {
        "quality_state": "partial",
        "fully_allocated_available": False,
        "unclassified_job_count": 1,
        "excluded_job_count": 2,
        "jobs": [
            {
                "result_id": "result-low",
                "result_digest": "a" * 64,
                "package_digest": "b" * 64,
                "computation_digest": "c" * 64,
                "authority_state": "current",
                "contribution_minor": -100,
                "quality_state": "partial",
            },
            {
                "result_id": "result-high",
                "result_digest": "d" * 64,
                "package_digest": "e" * 64,
                "computation_digest": "f" * 64,
                "authority_state": "current",
                "contribution_minor": 500,
                "quality_state": "complete",
            },
            {
                "result_id": "result-missing",
                "result_digest": "1" * 64,
                "package_digest": "2" * 64,
                "computation_digest": "3" * 64,
                "authority_state": "current",
                "contribution_minor": None,
                "quality_state": "stale",
            },
        ],
        "service_categories": [{"label": "Repair", "contribution_minor": 400}],
        "branches": [{"label": "Main", "contribution_minor": 400}],
        "comparison": {"state": "unavailable", "reason": "incomplete"},
        "period": {"start": "2026-08-01", "end": "2026-08-31"},
        "currency": "USD",
        "source_result_count": 3,
        "job_count": 3,
        "customers": [{"label": "Synthetic Customer"}],
        "totals": {"revenue": 1000, "labor": 300, "materials": 200},
        "readiness": {
            "policy_gaps": [{"gap_key": "allocation", "state": "open"}],
            "allocation_authority": {"state": "policy_required"},
        },
        "beacon_conditions": [
            {"kind": "incomplete_economic_evidence", "state": "partial"}
        ],
    }


def test_owner_questions_are_bounded_deterministic_and_truthful() -> None:
    value = projection()
    lowest = OwnerIntelligenceService._select(
        OwnerQuestion.LEAST_PROFITABLE_JOBS, value
    )
    highest = OwnerIntelligenceService._select(
        OwnerQuestion.MOST_PROFITABLE_JOBS, value
    )
    incomplete = OwnerIntelligenceService._select(
        OwnerQuestion.INCOMPLETE_MEASUREMENTS, value
    )
    assert [item["result_id"] for item in lowest["items"]] == [
        "result-low",
        "result-high",
    ]
    assert [item["result_id"] for item in highest["items"]] == [
        "result-high",
        "result-low",
    ]
    assert len(incomplete["items"]) <= MAX_CONTEXT_ITEMS
    assert incomplete["excluded_job_count"] == 2
    assert OwnerIntelligenceService._classification(value) == "INCOMPLETE"
    assert OwnerIntelligenceService._limitations(value) == [
        "economic_evidence_is_not_complete",
        "allocated_profitability_unavailable",
        "service_category_attribution_incomplete",
    ]


def test_context_references_expose_stable_economics_ids_only() -> None:
    answer = OwnerIntelligenceService._select(
        OwnerQuestion.LEAST_PROFITABLE_JOBS, projection()
    )
    assert OwnerIntelligenceService._references(answer) == [
        {
            "domain": "business-economics",
            "entity_type": "profitability_result",
            "entity_id": "result-low",
            "evidence_digest": "a" * 64,
            "package_digest": "b" * 64,
            "computation_digest": "c" * 64,
            "authority_state": "current",
        },
        {
            "domain": "business-economics",
            "entity_type": "profitability_result",
            "entity_id": "result-high",
            "evidence_digest": "d" * 64,
            "package_digest": "e" * 64,
            "computation_digest": "f" * 64,
            "authority_state": "current",
        },
    ]


def test_expanded_owner_questions_explain_changes_and_blockers() -> None:
    value = projection()
    value["comparison"] = {
        "state": "available",
        "labor_change_minor": 40,
        "materials_change_minor": -10,
    }
    labor = OwnerIntelligenceService._select(OwnerQuestion.LABOR_COST_MOVEMENT, value)
    blockers = OwnerIntelligenceService._select(
        OwnerQuestion.FULL_PROFITABILITY_BLOCKERS, value
    )
    decisions = OwnerIntelligenceService._select(
        OwnerQuestion.OWNER_DECISIONS_REQUIRED, value
    )
    inspect = OwnerIntelligenceService._select(OwnerQuestion.INSPECT_FIRST, value)
    assert labor["change_minor"] == 40
    assert "does not establish causality" in labor["limitation"]
    assert blockers["fully_allocated_available"] is False
    assert decisions["kind"] == "owner_decisions"
    assert inspect["items"]
