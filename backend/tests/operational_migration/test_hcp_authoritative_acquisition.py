import pytest

from app.operational_migration.hcp_authoritative_acquisition import (
    CollectionSeal,
    CrosswalkState,
    EvidenceAvailability,
    NativeControlEvidence,
    classify_relationship,
    seal_reconciliation_summary,
)


def test_collection_seal_requires_get_stability_and_unique_ids() -> None:
    seal = CollectionSeal("jobs", "GET /jobs", 2, ("a" * 64,), 2, True)
    assert len(seal.validate()) == 64
    with pytest.raises(ValueError, match="unique native"):
        CollectionSeal("jobs", "GET /jobs", 2, ("a" * 64,), 1, True).validate()
    with pytest.raises(ValueError, match="replay"):
        CollectionSeal("jobs", "GET /jobs", 2, ("a" * 64,), 2, False).validate()


def test_crosswalk_never_promotes_number_only_evidence_to_available() -> None:
    assert (
        NativeControlEvidence("job_native", "exported-job-number", ()).state
        == CrosswalkState.PARTIAL
    )
    assert NativeControlEvidence(
        "job_native", "exported-job-number", ("amount", "scheduled_date")
    ).state == CrosswalkState.AVAILABLE
    assert (
        NativeControlEvidence("job_native", None, ()).state
        == CrosswalkState.CONTROL_EXPORT_MISSING
    )


def test_missing_relationship_remains_partial_or_absent() -> None:
    assert (
        classify_relationship(parent_present=True, child_present=False)
        == EvidenceAvailability.PARTIAL
    )
    assert (
        classify_relationship(parent_present=False, child_present=False)
        == EvidenceAvailability.ABSENT
    )
    assert classify_relationship(
        parent_present=True, child_present=True, values_conflict=True
    ) == EvidenceAvailability.CONFLICTING


def test_safe_summary_rejects_source_data() -> None:
    assert len(seal_reconciliation_summary({"jobs": 5801, "state": "PARTIAL"})) == 64
    with pytest.raises(ValueError, match="identifying"):
        seal_reconciliation_summary({"email": "fixture@example.invalid"})
