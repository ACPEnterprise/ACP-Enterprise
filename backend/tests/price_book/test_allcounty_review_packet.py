import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "pricebook_allcounty_review", ROOT / "scripts/pricebook_allcounty_review.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def configuration():
    return json.loads(
        (
            ROOT / "docs/architecture/price-book/all-county-build-1.configuration.json"
        ).read_text()
    )


def test_packet_classifies_all_218_without_activation() -> None:
    packet = MODULE.build_packet(configuration())

    assert packet["service_candidate_count"] == 218
    assert sum(packet["classification_counts"].values()) == 218
    assert packet["classification_counts"].get("READY_FOR_ACTIVATION", 0) == 0
    assert {row["activation_status"] for row in packet["services"]} == {"NOT_ACTIVATED"}
    assert packet["controls"] == {
        "bulk_activation_supported": False,
        "automatic_activation_supported": False,
        "missing_values_default_to_zero": False,
        "human_activation_required": True,
    }
    assert packet["packet_digest"] == MODULE.canonical_digest(
        {key: value for key, value in packet.items() if key != "packet_digest"}
    )


def test_828627_conflict_requires_bounded_operator_decision() -> None:
    packet = MODULE.build_packet(configuration())
    conflict = next(
        value
        for value in packet["source_part_conflicts"]
        if value["candidate_identity"] == "vendor-unresolved:828627"
    )
    assert conflict["source_rows"] == [43, 64]
    assert conflict["resolution_state"] == "CONFLICTING"
    assert conflict["decision"] is None
    assert conflict["source_evidence_preserved"] is True

    resolved = MODULE.build_packet(
        configuration(),
        {
            "conflict_decisions": {
                "vendor-unresolved:828627": {
                    "decision": "KEEP_BOTH",
                    "decided_by": "owner",
                    "decided_at": "2026-09-12T12:00:00Z",
                    "reason": "Distinct reviewed source rows.",
                }
            }
        },
    )
    result = next(
        value
        for value in resolved["source_part_conflicts"]
        if value["candidate_identity"] == "vendor-unresolved:828627"
    )
    assert result["resolution_state"] == "RESOLVED_FOR_REVIEW"
    assert result["activation_status"] == "NOT_ACTIVATED"


def test_missing_price_is_not_coerced_to_zero() -> None:
    source = configuration()
    changed = copy.deepcopy(source)
    changed["service_candidates"][0]["price_candidates"]["standard"] = None
    packet = MODULE.build_packet(changed)
    row = packet["services"][0]
    assert row["proposed_standard_price"] is None
    assert "MISSING_PRICING_EVIDENCE" in {
        reason["code"] for reason in row["missing_evidence_reasons"]
    }


def test_rejects_unrecognized_conflict_decision() -> None:
    with pytest.raises(ValueError, match="Unsupported conflict decision"):
        MODULE.build_packet(
            configuration(),
            {"conflict_decisions": {"vendor-unresolved:828627": {"decision": "MERGE"}}},
        )
