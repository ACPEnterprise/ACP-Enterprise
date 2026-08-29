import pytest

from app.operational_migration.hcp_migration_rehearsal import (
    CandidateDisposition,
    DecisionPattern,
    MigrationCandidate,
    RelationshipEvidence,
    build_rehearsal_result,
    canonical_sha256,
    seal_candidates,
    verify_company_scope,
    verify_manifest_self_digest,
)


def candidate(native_id: str) -> MigrationCandidate:
    return MigrationCandidate(
        entity="job",
        native_id=native_id,
        source_digest=canonical_sha256({"id": native_id, "status": "dirty"}),
        history_layer="enterprise_analytical_history",
        disposition=CandidateDisposition.EXPLICIT_EXCEPTION,
        relationship_evidence=RelationshipEvidence.PARTIAL,
        exception_codes=("control_export_missing",),
    )


def test_candidate_seal_is_order_independent_and_duplicate_safe() -> None:
    assert seal_candidates((candidate("a"), candidate("b"))) == seal_candidates(
        (candidate("b"), candidate("a"))
    )
    with pytest.raises(ValueError, match="duplicate provider-native"):
        seal_candidates((candidate("a"), candidate("a")))


def test_manifest_verification_fails_closed() -> None:
    manifest = {"provider": "housecall_pro", "count": 2}
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    assert verify_manifest_self_digest(manifest) == manifest["manifest_sha256"]
    manifest["count"] = 3
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_manifest_self_digest(manifest)


def test_rehearsal_replay_is_deterministic_and_keeps_exceptions() -> None:
    pattern = DecisionPattern(
        "day_one_balance",
        1,
        1,
        ("migrate_as_open", "exclude_with_evidence"),
        canonical_sha256({"records": 1}),
    )
    result = build_rehearsal_result(
        source_package_sha256="a" * 64,
        candidates=(candidate("b"), candidate("a")),
        decision_patterns=(pattern,),
    )
    assert result.deterministic
    assert result.candidate_counts == {"job": 2}
    assert result.exception_counts == {"control_export_missing": 2}


def test_company_scope_rejects_cross_company_candidates() -> None:
    assert verify_company_scope(("a" * 64, "a" * 64)) == "a" * 64
    with pytest.raises(ValueError, match="exactly one Company"):
        verify_company_scope(("a" * 64, "b" * 64))
