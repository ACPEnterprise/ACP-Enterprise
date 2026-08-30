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
