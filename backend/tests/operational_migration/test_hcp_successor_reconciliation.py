import pytest
from app.operational_migration.hcp_successor_reconciliation import (
    IdentityBinding,
    SealedIdentity,
    SuccessorDisposition,
    reconcile_successors,
)


def binding(
    system: str, source: str, target: str, domain: str = "customer"
) -> IdentityBinding:
    return IdentityBinding(domain, system, source, target)


def test_reconciliation_classifies_exact_replacement_and_ambiguity_without_ids() -> (
    None
):
    report = reconcile_successors(
        current_bindings=[
            binding("housecall_pro", "a", "native-1"),
            binding("housecall_pro_source4", "a", "native-1"),
            binding("housecall_pro", "b", "native-2"),
            binding("housecall_pro_source4", "c", "native-3"),
        ],
        sealed_source4=[SealedIdentity("customer", value) for value in ("a", "b", "c")],
    )
    assert report.disposition_counts == {
        SuccessorDisposition.EXACT_SUCCESSOR: 1,
        SuccessorDisposition.AMBIGUOUS: 1,
        SuccessorDisposition.CONTROLLED_REPLACEMENT: 1,
    }
    assert report.admission_allowed is False
    rendered = repr(report)
    assert all(value not in rendered for value in ("native-1", "native-2", "native-3"))


def test_reconciliation_is_order_independent_and_replacement_only_is_admissible() -> (
    None
):
    sealed = [SealedIdentity("job", "2"), SealedIdentity("job", "1")]
    first = reconcile_successors(current_bindings=[], sealed_source4=sealed)
    replay = reconcile_successors(current_bindings=[], sealed_source4=reversed(sealed))
    assert first == replay
    assert first.admission_allowed is True
    assert first.domain_counts["job"][SuccessorDisposition.CONTROLLED_REPLACEMENT] == 2


def test_duplicate_sealed_identity_fails_closed() -> None:
    sealed = [SealedIdentity("appointment", "same")] * 2
    with pytest.raises(ValueError, match="contains duplicates"):
        reconcile_successors(current_bindings=[], sealed_source4=sealed)


def test_unsupported_source_system_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported source system"):
        reconcile_successors(
            current_bindings=[binding("other", "x", "native")],
            sealed_source4=[SealedIdentity("customer", "x")],
        )


def test_legacy_identity_absent_from_sealed_authority_is_ambiguous() -> None:
    report = reconcile_successors(
        current_bindings=[binding("housecall_pro", "pilot-only", "native")],
        sealed_source4=[],
    )
    assert report.disposition_counts[SuccessorDisposition.AMBIGUOUS] == 1
    assert report.admission_allowed is False
