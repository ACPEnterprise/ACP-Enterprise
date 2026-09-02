import json
from collections import Counter
from pathlib import Path

PACKET = (
    Path(__file__).parents[3]
    / "docs/architecture/price-book/all-county-build-1.configuration.json"
)


def test_allcounty_packet_is_complete_non_activating_and_row_accounted() -> None:
    packet = json.loads(PACKET.read_text())
    registrations = packet["source_registrations"]

    assert len(registrations) == 7
    assert all(source["readable"] and source["sha256"] for source in registrations)
    assert packet["activation_status"] == "NOT_ACTIVATED"
    assert len(packet["categories"]) == 16
    assert len(packet["service_candidates"]) == 218
    assert (
        len({item["candidate_identity"] for item in packet["service_candidates"]})
        == 218
    )
    assert all(
        item["activation_status"] == "NOT_ACTIVATED"
        for item in packet["service_candidates"]
    )

    derivations = Counter(
        item["price_derivation"] for item in packet["service_candidates"]
    )
    assert derivations == {"WORKBOOK_FORMULA": 208, "OWNER_OVERRIDE": 10}
    assert all(
        item["labor"]["authority"] == "CONFIGURED_ESTIMATE"
        for item in packet["service_candidates"]
    )
    assert all(
        item["tax_review"] == "OWNER_ACCOUNTANT_REVIEW_REQUIRED"
        for item in packet["service_candidates"]
    )


def test_vendor_materials_and_water_heater_reconciliation_fail_closed() -> None:
    packet = json.loads(PACKET.read_text())
    materials = packet["vendor_material_import"]
    water_heater = packet["water_heater_reconciliation"]

    assert materials["candidate_count"] == 361
    assert materials["unique_candidate_identity_count"] == 360
    assert materials["maximum_hierarchy_depth"] == 4
    assert materials["duplicate_candidate_identities"] == {
        "vendor-unresolved:828627": [43, 64]
    }
    assert all(not item["inventory_mutation"] for item in materials["candidates"])
    assert all(
        not item["customer_facing_service_creation"] for item in materials["candidates"]
    )
    assert water_heater["existing_candidate_count"] == 39
    assert water_heater["new_service_candidates"] == 0
    assert water_heater["scope_reconciliation"] == "CONSISTENT"
    assert water_heater["price_examples"] == "CONFLICTING"
    assert water_heater["component_cost_breakdown"] == "ILLUSTRATIVE_ASSUMPTION"
    assert water_heater["activation_status"] == "NOT_ACTIVATED"
