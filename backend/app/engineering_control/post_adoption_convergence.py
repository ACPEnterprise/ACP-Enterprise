from dataclasses import dataclass


@dataclass(frozen=True)
class AdoptedOwnerReviewFacts:
    execution_succeeded: bool
    adopted_result_verified: bool
    published_repository_mutation: bool
    pending_review_count: int
    review_matches_lineage: bool
    scheduler_matches_lineage: bool
    superseded: bool
    active_authority: bool
    unresolved_recovery: bool


@dataclass(frozen=True)
class AdoptedOwnerReviewDecision:
    eligible: bool
    reason: str


def evaluate_adopted_owner_review(
    facts: AdoptedOwnerReviewFacts,
) -> AdoptedOwnerReviewDecision:
    """Apply the fail-closed precedence rule for an adopted published result."""
    checks = (
        (facts.execution_succeeded, "execution_not_successful"),
        (facts.adopted_result_verified, "adopted_result_not_verified"),
        (
            facts.published_repository_mutation,
            "published_repository_mutation_not_verified",
        ),
        (facts.pending_review_count == 1, "pending_review_ambiguous"),
        (facts.review_matches_lineage, "review_lineage_mismatch"),
        (facts.scheduler_matches_lineage, "scheduler_lineage_mismatch"),
        (not facts.superseded, "execution_lineage_superseded"),
        (not facts.active_authority, "active_execution_authority"),
        (not facts.unresolved_recovery, "unresolved_recovery_evidence"),
    )
    for accepted, reason in checks:
        if not accepted:
            return AdoptedOwnerReviewDecision(False, reason)
    return AdoptedOwnerReviewDecision(True, "adopted_result_owner_review")
