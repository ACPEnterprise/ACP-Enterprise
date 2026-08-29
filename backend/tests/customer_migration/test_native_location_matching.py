from dataclasses import replace
from uuid import UUID

from app.customer_migration.native_location_matching import (
    AcquiredNativeLocation,
    EnterpriseLocationCandidate,
    NativeLocationMatchOutcome,
    match_native_location,
)

COMPANY = UUID("00000000-0000-0000-0000-000000000001")
BRANCH = UUID("00000000-0000-0000-0000-000000000002")
CUSTOMER_SOURCE = UUID("00000000-0000-0000-0000-000000000003")
EVIDENCE = UUID("00000000-0000-0000-0000-000000000004")
CUSTOMER = UUID("00000000-0000-0000-0000-000000000005")
LOCATION = UUID("00000000-0000-0000-0000-000000000006")


def acquired(**changes: object) -> AcquiredNativeLocation:
    values: dict[str, object] = {
        "identity_evidence_id": EVIDENCE,
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "source_location_id_sha256": "a" * 64,
        "source_customer_id_sha256": "b" * 64,
        "customer_source_identity_id": CUSTOMER_SOURCE,
        "normalized_address_sha256": "c" * 64,
        "readiness": "ready",
        "evidence_digest": "d" * 64,
    }
    values.update(changes)
    return AcquiredNativeLocation(**values)  # type: ignore[arg-type]


def candidate(**changes: object) -> EnterpriseLocationCandidate:
    values: dict[str, object] = {
        "service_location_id": LOCATION,
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "customer_id": CUSTOMER,
        "customer_source_identity_id": CUSTOMER_SOURCE,
        "source_customer_id_sha256": "b" * 64,
        "normalized_address_sha256": "c" * 64,
        "source_location_id_sha256": "a" * 64,
    }
    values.update(changes)
    return EnterpriseLocationCandidate(**values)  # type: ignore[arg-type]


def test_exact_native_identity_matches_and_replays_deterministically() -> None:
    source = acquired()
    options = (candidate(),)
    first = match_native_location(source, options)
    second = match_native_location(source, options)
    assert first == second
    assert first.outcome is NativeLocationMatchOutcome.MATCHED
    assert first.service_location_id == LOCATION
    assert first.customer_id == CUSTOMER


def test_duplicate_native_identity_fails_closed() -> None:
    result = match_native_location(
        acquired(),
        (candidate(), candidate(service_location_id=UUID(int=7))),
    )
    assert result.outcome is NativeLocationMatchOutcome.DUPLICATE_NATIVE_IDENTITY
    assert result.service_location_id is None
    assert result.candidate_count == 2


def test_parent_and_existing_binding_conflicts_fail_closed() -> None:
    parent = match_native_location(
        acquired(), (candidate(customer_source_identity_id=UUID(int=8)),)
    )
    assert parent.outcome is NativeLocationMatchOutcome.PARENT_MISMATCH
    binding = match_native_location(
        acquired(accepted_service_location_id=UUID(int=9)), (candidate(),)
    )
    assert binding.outcome is NativeLocationMatchOutcome.EXISTING_BINDING_CONFLICT


def test_company_or_branch_crossing_is_a_scope_conflict() -> None:
    result = match_native_location(
        acquired(), (candidate(company_id=UUID(int=10), branch_id=UUID(int=11)),)
    )
    assert result.outcome is NativeLocationMatchOutcome.COMPANY_BRANCH_SCOPE_CONFLICT
    assert result.service_location_id is None


def test_address_equality_never_creates_an_identity_binding() -> None:
    address_only = replace(candidate(), source_location_id_sha256=None)
    result = match_native_location(acquired(), (address_only,))
    assert result.outcome is NativeLocationMatchOutcome.ADDRESS_REVIEW_REQUIRED
    assert result.service_location_id is None


def test_multiple_address_matches_are_ambiguous() -> None:
    first = replace(candidate(), source_location_id_sha256=None)
    second = replace(first, service_location_id=UUID(int=12))
    result = match_native_location(acquired(), (first, second))
    assert result.outcome is NativeLocationMatchOutcome.AMBIGUOUS_ADDRESS
    assert result.candidate_count == 2


def test_unready_identity_and_no_match_are_distinct() -> None:
    unready = match_native_location(acquired(readiness="reconciliation_required"), ())
    assert unready.outcome is NativeLocationMatchOutcome.IDENTITY_NOT_READY
    missing = match_native_location(acquired(), ())
    assert missing.outcome is NativeLocationMatchOutcome.NO_MATCH
