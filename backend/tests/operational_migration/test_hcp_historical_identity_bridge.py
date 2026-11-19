import pytest
from app.operational_migration.hcp_historical_identity_bridge import (
    AddressEvidence,
    BridgeDisposition,
    CanonicalCustomerEvidence,
    CanonicalLocationEvidence,
    SourceCustomerEvidence,
    build_historical_identity_bridge,
)


def address(identity: str, line: str = "123 Main St") -> AddressEvidence:
    return AddressEvidence(identity, line, None, "Clearwater", "FL", "33755")


def canonical(
    identity: str,
    *,
    name: str = "Richard Ratliff",
    email: str | None = "richard@example.test",
    phone: str = "727-555-0101",
    line: str = "123 Main St",
    source_ids: tuple[str, ...] = (),
) -> CanonicalCustomerEvidence:
    return CanonicalCustomerEvidence(
        native_customer_id=identity,
        display_name=name,
        email=email,
        phones=(phone,),
        locations=(
            CanonicalLocationEvidence(f"location-{identity}", address("", line)),
        ),
        existing_source_ids=source_ids,
    )


def source(
    identity: str,
    *,
    name: str = "Richard Ratliff",
    email: str | None = "RICHARD@example.test",
    phone: str = "(727) 555-0101",
    line: str = "123 MAIN ST",
    successor: str | None = None,
) -> SourceCustomerEvidence:
    return SourceCustomerEvidence(
        source_customer_id=identity,
        display_name=name,
        email=email,
        phones=(phone,),
        locations=(address(f"source-location-{identity}", line),),
        successor_native_id=successor,
    )


def test_corroborated_exact_customer_and_location_bridge() -> None:
    result = build_historical_identity_bridge(
        source=(source("opaque-richard"),), canonical=(canonical("native-richard"),)
    )

    assert result.bridged == 1
    assert result.unexplained == 0
    [decision] = result.decisions
    assert decision.disposition is BridgeDisposition.CORROBORATED_EXACT
    assert decision.evidence_dimensions == ("address", "email", "name", "phone")
    assert decision.locations[0].native_location_id == "location-native-richard"
    result.verify()


def test_name_and_address_alone_do_not_establish_customer_identity() -> None:
    result = build_historical_identity_bridge(
        source=(source("opaque", email=None, phone=""),),
        canonical=(canonical("native", email=None, phone=""),),
    )

    assert result.quarantined == 1
    assert result.decisions[0].native_customer_id is None


def test_multiple_corroborated_candidates_are_ambiguous() -> None:
    result = build_historical_identity_bridge(
        source=(source("opaque"),),
        canonical=(canonical("one"), canonical("two")),
    )

    assert result.ambiguous == 1
    assert result.decisions[0].candidate_native_ids == ("one", "two")


def test_exact_successor_lineage_wins_without_contact_inference() -> None:
    result = build_historical_identity_bridge(
        source=(
            source(
                "opaque", name="Changed Name", email=None, phone="", successor="native"
            ),
        ),
        canonical=(canonical("native"),),
    )

    assert result.decisions[0].disposition is BridgeDisposition.EXACT_LINEAGE


def test_duplicate_target_claim_is_prevented_and_explained() -> None:
    result = build_historical_identity_bridge(
        source=(source("opaque-1"), source("opaque-2")),
        canonical=(canonical("native"),),
    )

    assert result.bridged == 1
    assert result.ambiguous == 1
    assert result.duplicates_prevented == 1


def test_duplicate_source_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="source Customer identities must be unique"):
        build_historical_identity_bridge(
            source=(source("duplicate"), source("duplicate")), canonical=()
        )
