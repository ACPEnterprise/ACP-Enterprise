from dataclasses import replace

import pytest
from app.engineering_control.post_adoption_convergence import (
    AdoptedOwnerReviewFacts,
    evaluate_adopted_owner_review,
)


@pytest.fixture
def eligible_facts() -> AdoptedOwnerReviewFacts:
    return AdoptedOwnerReviewFacts(
        execution_succeeded=True,
        adopted_result_verified=True,
        published_repository_mutation=True,
        pending_review_count=1,
        review_matches_lineage=True,
        scheduler_matches_lineage=True,
        superseded=False,
        active_authority=False,
        unresolved_recovery=False,
    )


def test_adopted_published_result_precedes_stale_ready_projection(
    eligible_facts: AdoptedOwnerReviewFacts,
) -> None:
    decision = evaluate_adopted_owner_review(eligible_facts)

    assert decision.eligible is True
    assert decision.reason == "adopted_result_owner_review"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"execution_succeeded": False}, "execution_not_successful"),
        ({"adopted_result_verified": False}, "adopted_result_not_verified"),
        (
            {"published_repository_mutation": False},
            "published_repository_mutation_not_verified",
        ),
        ({"pending_review_count": 0}, "pending_review_ambiguous"),
        ({"pending_review_count": 2}, "pending_review_ambiguous"),
        ({"review_matches_lineage": False}, "review_lineage_mismatch"),
        ({"scheduler_matches_lineage": False}, "scheduler_lineage_mismatch"),
        ({"superseded": True}, "execution_lineage_superseded"),
        ({"active_authority": True}, "active_execution_authority"),
        ({"unresolved_recovery": True}, "unresolved_recovery_evidence"),
    ],
)
def test_adopted_owner_review_convergence_fails_closed(
    eligible_facts: AdoptedOwnerReviewFacts,
    changes: dict[str, object],
    reason: str,
) -> None:
    decision = evaluate_adopted_owner_review(replace(eligible_facts, **changes))

    assert decision.eligible is False
    assert decision.reason == reason
