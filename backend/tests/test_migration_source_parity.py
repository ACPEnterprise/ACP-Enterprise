import pytest

from app.migration_source_parity import (
    ParityDisposition,
    SourceDisposition,
    build_source_parity_certificate,
)


def disposition(
    family: str, identity: str, state: ParityDisposition
) -> SourceDisposition:
    return SourceDisposition(
        family=family,
        provider_record_id=identity,
        disposition=state,
        explanation="deterministic test disposition",
        canonical_id=(
            f"native-{identity}"
            if state is ParityDisposition.CANONICAL
            else None
        ),
    )


def test_certificate_accounts_for_canonical_quarantine_and_provider_failure() -> None:
    result = build_source_parity_certificate(
        provider="housecall_pro",
        source_as_of="2026-11-18T00:00:00Z",
        source_identities={"customers": ("1", "2", "3"), "refunds": ("r1",)},
        dispositions=(
            disposition("customers", "1", ParityDisposition.CANONICAL),
            disposition("customers", "2", ParityDisposition.QUARANTINED),
            disposition("customers", "3", ParityDisposition.PROVIDER_UNAVAILABLE),
            disposition("refunds", "r1", ParityDisposition.CANONICAL),
        ),
        required_families=("customers", "refunds"),
    )

    assert result.complete is True
    assert result.unexplained_delta == 0
    assert result.domains[0].source_count == 3
    assert result.domains[0].canonical_count == 1
    assert result.domains[0].quarantined == 1
    assert result.domains[0].provider_unavailable == 1
    result.verify()


def test_missing_disposition_is_an_unexplained_delta_and_blocks_completion() -> None:
    result = build_source_parity_certificate(
        provider="quickbooks_online",
        source_as_of="2025-12-31",
        source_identities={"accounts": ("1", "2")},
        dispositions=(disposition("accounts", "1", ParityDisposition.CANONICAL),),
        required_families=("accounts",),
    )

    assert result.complete is False
    assert result.unexplained_delta == 1
    assert result.domains[0].unexplained_delta == 1


def test_duplicate_or_non_source_dispositions_are_rejected() -> None:
    item = disposition("customers", "1", ParityDisposition.CANONICAL)
    with pytest.raises(ValueError, match="multiple current dispositions"):
        build_source_parity_certificate(
            provider="hcp",
            source_as_of="now",
            source_identities={"customers": ("1",)},
            dispositions=(item, item),
            required_families=("customers",),
        )
    with pytest.raises(ValueError, match="no acquired source identity"):
        build_source_parity_certificate(
            provider="hcp",
            source_as_of="now",
            source_identities={"customers": ("1",)},
            dispositions=(
                disposition("customers", "2", ParityDisposition.CANONICAL),
            ),
            required_families=("customers",),
        )
