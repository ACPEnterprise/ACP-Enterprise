import pytest
from app.operational_migration.hcp_legacy_projection_classification import (
    LegacyProjectionDisposition,
    ProjectionCorrelationEvidence,
    classify_correlated_legacy,
    classify_legacy_projections,
)
from app.operational_migration.hcp_successor_reconciliation import (
    IdentityBinding,
    SealedIdentity,
)


def binding(domain: str, system: str, source: str, target: str) -> IdentityBinding:
    return IdentityBinding(domain, system, source, target)


def test_classifies_complete_union_and_preserves_canonical_blocker() -> None:
    result = classify_legacy_projections(
        current_bindings=(
            binding("customer", "housecall_pro", "reuse", "one"),
            binding("job", "housecall_pro", "done", "two"),
            binding("job", "housecall_pro_source4", "done", "two"),
            binding("invoice", "housecall_pro", "outside", "three"),
        ),
        sealed_source4=(
            SealedIdentity("customer", "reuse"),
            SealedIdentity("job", "done"),
            SealedIdentity("appointment", "new"),
        ),
    )
    assert [item.disposition for item in result.records] == [
        LegacyProjectionDisposition.SEALED_CREATE_NEW,
        LegacyProjectionDisposition.EXACT_SUCCESSOR,
        LegacyProjectionDisposition.AMBIGUOUS_HOLD,
        LegacyProjectionDisposition.EXACT_SUCCESSOR,
    ]
    assert result.report.canonical_blocker_count == 1
    assert result.report.canonical_admission_allowed is False
    assert "three" not in repr(result.report)


@pytest.mark.parametrize(
    "domain",
    [
        "customer",
        "contact",
        "service_location",
        "job",
        "appointment",
        "estimate",
        "invoice",
        "payment",
    ],
)
def test_every_supported_domain_classifies_create_new(domain: str) -> None:
    result = classify_legacy_projections(
        current_bindings=(), sealed_source4=(SealedIdentity(domain, "source"),)
    )
    assert (
        result.records[0].disposition
        == LegacyProjectionDisposition.SEALED_CREATE_NEW
    )
    assert result.report.canonical_admission_allowed is True


def test_source4_without_matching_legacy_is_a_conflict() -> None:
    result = classify_legacy_projections(
        current_bindings=(
            binding("payment", "housecall_pro_source4", "source", "target"),
        ),
        sealed_source4=(SealedIdentity("payment", "source"),),
    )
    assert (
        result.records[0].disposition
        == LegacyProjectionDisposition.GENUINE_CONFLICT
    )
    assert result.report.canonical_blocker_count == 1


def test_target_collision_is_a_conflict() -> None:
    result = classify_legacy_projections(
        current_bindings=(
            binding("job", "housecall_pro", "one", "same"),
            binding("job", "housecall_pro", "two", "same"),
        ),
        sealed_source4=(SealedIdentity("job", "one"), SealedIdentity("job", "two")),
    )
    assert all(
        item.disposition == LegacyProjectionDisposition.GENUINE_CONFLICT
        for item in result.records
    )


def test_order_is_deterministic_and_report_is_identifier_free() -> None:
    bindings = (
        binding("estimate", "housecall_pro", "b", "target-b"),
        binding("estimate", "housecall_pro", "a", "target-a"),
    )
    sealed = (SealedIdentity("estimate", "b"), SealedIdentity("estimate", "a"))
    first = classify_legacy_projections(
        current_bindings=bindings, sealed_source4=sealed
    )
    replay = classify_legacy_projections(
        current_bindings=reversed(bindings), sealed_source4=reversed(sealed)
    )
    assert first == replay
    assert all(value not in repr(first.report) for value in ("target-a", "target-b"))


@pytest.mark.parametrize(
    "bindings,sealed",
    [
        ((), (SealedIdentity("unknown", "source"),)),
        ((binding("customer", "other", "source", "target"),), ()),
        ((binding("customer", "housecall_pro", "", "target"),), ()),
    ],
)
def test_invalid_evidence_fails_closed(
    bindings: tuple[IdentityBinding, ...], sealed: tuple[SealedIdentity, ...]
) -> None:
    with pytest.raises(ValueError):
        classify_legacy_projections(
            current_bindings=bindings, sealed_source4=sealed
        )


def test_correlated_classification_uses_unique_content_and_holds_negative_match() -> None:
    exact = "1" * 64
    missing = "2" * 64
    result = classify_correlated_legacy(
        legacy=(
            ProjectionCorrelationEvidence("customer", "old-a", "target-a", (exact,)),
            ProjectionCorrelationEvidence("customer", "old-b", "target-b", (missing,)),
        ),
        sealed=(
            ProjectionCorrelationEvidence("customer", "new-a", None, (exact,)),
        ),
    )
    assert [item.disposition for item in result.records] == [
        LegacyProjectionDisposition.EXACT_SUCCESSOR,
        LegacyProjectionDisposition.AMBIGUOUS_HOLD,
    ]
    assert result.report.canonical_blocker_count == 1


def test_authoritative_provider_nonmatch_proves_unrelated() -> None:
    result = classify_correlated_legacy(
        legacy=(
            ProjectionCorrelationEvidence(
                "job", "old", "target", authoritative_provider_id="provider-old"
            ),
        ),
        sealed=(
            ProjectionCorrelationEvidence(
                "job", "new", None, authoritative_provider_id="provider-new"
            ),
        ),
    )
    assert (
        result.records[0].disposition
        == LegacyProjectionDisposition.PROVABLY_UNRELATED
    )
    assert result.report.canonical_admission_allowed is True


def test_disagreeing_unique_signals_are_a_genuine_conflict() -> None:
    result = classify_correlated_legacy(
        legacy=(
            ProjectionCorrelationEvidence(
                "customer", "old", "target", ("1" * 64, "2" * 64)
            ),
        ),
        sealed=(
            ProjectionCorrelationEvidence("customer", "new-a", None, ("1" * 64,)),
            ProjectionCorrelationEvidence("customer", "new-b", None, ("2" * 64,)),
        ),
    )
    assert (
        result.records[0].disposition
        == LegacyProjectionDisposition.GENUINE_CONFLICT
    )
