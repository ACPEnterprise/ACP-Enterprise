from app.business_economics.source_completeness import source_completeness_matrix


def workspace(*, quality: str = "complete", allocation: bool = True):
    return {
        "period": {"start": "2026-07-01", "end": "2026-07-31"},
        "quality_state": quality,
        "source_result_count": 2,
        "job_count": 2,
        "unclassified_job_count": 0,
        "totals": {"revenue": 100, "labor": 40, "materials": 20},
        "jobs": [
            {"other_direct_cost_minor": 0},
            {"other_direct_cost_minor": 5},
        ],
        "fully_allocated_available": allocation,
        "readiness": {"policy_gaps": []},
    }


def states(value):
    return {item["source"]: item["state"] for item in value["sources"]}


def test_matrix_distinguishes_admitted_inputs_from_policy_and_partial_seams() -> None:
    value = source_completeness_matrix(workspace())
    assert states(value) == {
        "revenue": "AVAILABLE",
        "settlement": "POLICY_REQUIRED",
        "direct_labor": "AVAILABLE",
        "employer_burden": "PARTIAL",
        "materials": "AVAILABLE",
        "other_direct_cost": "AVAILABLE",
        "overhead_allocation": "AVAILABLE",
        "job_identity_lifecycle": "AVAILABLE",
        "service_category": "AVAILABLE",
        "accounting_evidence": "PARTIAL",
    }
    assert value["complete_for_direct_contribution"] is True
    assert value["complete_for_fully_allocated_profitability"] is False


def test_matrix_fails_closed_for_conflicting_evidence_and_missing_policy() -> None:
    conflicting = source_completeness_matrix(workspace(quality="conflicting"))
    assert states(conflicting)["revenue"] == "CONFLICTING"
    assert states(conflicting)["job_identity_lifecycle"] == "CONFLICTING"
    no_policy = source_completeness_matrix(workspace(allocation=False))
    assert states(no_policy)["overhead_allocation"] == "POLICY_REQUIRED"


def test_matrix_replay_digest_is_deterministic() -> None:
    assert (
        source_completeness_matrix(workspace())["matrix_digest"]
        == source_completeness_matrix(workspace())["matrix_digest"]
    )
