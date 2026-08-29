from uuid import UUID

import pytest

from app.customer_migration.cutover_readiness import (
    CutoverEvidenceSnapshot,
    CutoverPrerequisite,
    PrerequisiteStatus,
    ReadinessCategoryCount,
    assess_cutover_readiness,
)

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)


def prerequisite(
    code: str, status: PrerequisiteStatus = PrerequisiteStatus.COMPLETE
) -> CutoverPrerequisite:
    return CutoverPrerequisite(
        code, status, True, "a" * 64 if status is PrerequisiteStatus.COMPLETE else None
    )


def snapshot(**changes: object) -> CutoverEvidenceSnapshot:
    values: dict[str, object] = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "prerequisites": (
            prerequisite("customer_migration"),
            prerequisite("source_identity"),
        ),
        "owner_dispositions": (),
        "reconciliation_items": (),
        "source_evidence_digests": ("b" * 64,),
        "total_evidence_items": 10,
        "deterministically_resolved_items": 10,
    }
    values.update(changes)
    return CutoverEvidenceSnapshot(**values)  # type: ignore[arg-type]


def test_ready_assessment_is_deterministic_and_review_only() -> None:
    first = assess_cutover_readiness(snapshot())
    second = assess_cutover_readiness(snapshot())
    assert first == second
    assert first.ready is True
    assert first.status == "ready_for_owner_review"
    assert first.confidence_basis_points == 10000
    assert first.completeness_basis_points == 10000


def test_missing_and_blocked_prerequisites_fail_closed() -> None:
    result = assess_cutover_readiness(
        snapshot(
            prerequisites=(
                prerequisite("complete"),
                prerequisite("missing", PrerequisiteStatus.MISSING),
                prerequisite("blocked", PrerequisiteStatus.BLOCKED),
            )
        )
    )
    assert result.ready is False
    assert result.missing_prerequisites == ("blocked", "missing")
    assert result.completeness_basis_points == 3333


def test_owner_dispositions_and_reconciliation_are_blockers() -> None:
    result = assess_cutover_readiness(
        snapshot(
            owner_dispositions=(ReadinessCategoryCount("ambiguous_customer", 2),),
            reconciliation_items=(ReadinessCategoryCount("parent_mismatch", 1),),
        )
    )
    assert result.ready is False
    assert "owner_disposition:ambiguous_customer" in result.blocking_conditions
    assert "reconciliation:parent_mismatch" in result.blocking_conditions


def test_confidence_measures_deterministically_resolved_evidence() -> None:
    result = assess_cutover_readiness(
        snapshot(total_evidence_items=8, deterministically_resolved_items=6)
    )
    assert result.confidence_basis_points == 7500
    assert "evidence:incomplete_resolution" in result.blocking_conditions


def test_missing_evidence_digest_fails_closed() -> None:
    result = assess_cutover_readiness(snapshot(source_evidence_digests=()))
    assert result.ready is False
    assert "evidence:missing_source_digests" in result.blocking_conditions


def test_contract_invariants_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="requires immutable evidence"):
        CutoverPrerequisite("invalid", PrerequisiteStatus.COMPLETE, True, None)
    with pytest.raises(ValueError, match="do not reconcile"):
        snapshot(total_evidence_items=1, deterministically_resolved_items=2)
    with pytest.raises(ValueError, match="must be unique"):
        snapshot(prerequisites=(prerequisite("same"), prerequisite("same")))
