from uuid import UUID

from app.customer_migration.native_customer_consolidation import (
    EnterpriseCustomerIdentityCandidate,
    NativeCustomerConsolidationOutcome,
    NativeCustomerObservation,
    consolidate_native_customers,
)
from app.customer_migration.native_location_identity import scoped_identity

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)
SOURCE_IDENTITY = UUID(int=3)
CUSTOMER = UUID(int=4)


def observation(
    native_id: str | None = "customer-1", **changes: object
) -> NativeCustomerObservation:
    values: dict[str, object] = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "provider": "provider-a",
        "native_customer_id": native_id,
        "source_artifact_sha256": "a" * 64,
        "source_record_sha256": "b" * 64,
    }
    values.update(changes)
    return NativeCustomerObservation(**values)  # type: ignore[arg-type]


def candidate(
    native_id: str = "customer-1", **changes: object
) -> EnterpriseCustomerIdentityCandidate:
    values: dict[str, object] = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "customer_source_identity_id": SOURCE_IDENTITY,
        "customer_id": CUSTOMER,
        "source_customer_id_sha256": scoped_identity(
            "provider-a", "customer", native_id
        ),
    }
    values.update(changes)
    return EnterpriseCustomerIdentityCandidate(**values)  # type: ignore[arg-type]


def test_exact_identity_resolves_and_replays_deterministically() -> None:
    inputs = (observation(),)
    options = (candidate(),)
    first = consolidate_native_customers(inputs, options)
    second = consolidate_native_customers(inputs, options)
    assert first == second
    assert first[0].outcome is NativeCustomerConsolidationOutcome.RESOLVED
    assert first[0].customer_id == CUSTOMER


def test_missing_and_unresolved_identities_are_distinct() -> None:
    missing = consolidate_native_customers((observation(None),), ())
    assert (
        missing[0].outcome
        is NativeCustomerConsolidationOutcome.MISSING_SOURCE_IDENTIFIER
    )
    unresolved = consolidate_native_customers((observation(),), ())
    assert unresolved[0].outcome is NativeCustomerConsolidationOutcome.UNRESOLVED


def test_duplicate_source_evidence_fails_closed() -> None:
    duplicate = consolidate_native_customers(
        (observation(), observation()), (candidate(),)
    )
    assert (
        duplicate[0].outcome
        is NativeCustomerConsolidationOutcome.DUPLICATE_SOURCE_EVIDENCE
    )
    assert duplicate[0].customer_id is None


def test_conflicting_claims_and_existing_binding_fail_closed() -> None:
    conflict = consolidate_native_customers(
        (
            observation(claimed_customer_id=UUID(int=8)),
            observation(source_record_sha256="c" * 64, claimed_customer_id=UUID(int=9)),
        ),
        (candidate(),),
    )
    assert (
        conflict[0].outcome
        is NativeCustomerConsolidationOutcome.CONFLICTING_SOURCE_EVIDENCE
    )
    binding = consolidate_native_customers(
        (observation(claimed_customer_id=UUID(int=8)),), (candidate(),)
    )
    assert (
        binding[0].outcome
        is NativeCustomerConsolidationOutcome.EXISTING_BINDING_CONFLICT
    )


def test_ambiguous_target_and_scope_crossing_fail_closed() -> None:
    ambiguous = consolidate_native_customers(
        (observation(),),
        (
            candidate(),
            candidate(
                customer_source_identity_id=UUID(int=10), customer_id=UUID(int=11)
            ),
        ),
    )
    assert ambiguous[0].outcome is NativeCustomerConsolidationOutcome.AMBIGUOUS_TARGET
    scope = consolidate_native_customers(
        (observation(),), (candidate(company_id=UUID(int=12), branch_id=UUID(int=13)),)
    )
    assert (
        scope[0].outcome
        is NativeCustomerConsolidationOutcome.COMPANY_BRANCH_SCOPE_CONFLICT
    )


def test_multiple_source_versions_consolidate_when_not_duplicate() -> None:
    result = consolidate_native_customers(
        (
            observation(),
            observation(source_artifact_sha256="d" * 64, source_record_sha256="e" * 64),
        ),
        (candidate(),),
    )
    assert result[0].outcome is NativeCustomerConsolidationOutcome.RESOLVED
    assert result[0].observation_count == 2


def test_multiple_native_identities_for_one_customer_require_review() -> None:
    results = consolidate_native_customers(
        (
            observation("customer-1"),
            observation("customer-2", source_record_sha256="c" * 64),
        ),
        (
            candidate("customer-1"),
            candidate("customer-2", customer_source_identity_id=UUID(int=14)),
        ),
    )
    assert {item.outcome for item in results} == {
        NativeCustomerConsolidationOutcome.MULTIPLE_NATIVE_IDENTITIES_ONE_CUSTOMER
    }
    assert all(item.customer_id is None for item in results)
