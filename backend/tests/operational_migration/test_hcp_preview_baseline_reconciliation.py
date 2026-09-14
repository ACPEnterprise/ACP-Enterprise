from __future__ import annotations

import copy

import pytest

from app.operational_migration.hcp_preview_baseline_reconciliation import (
    EXPECTED,
    semantic_digest,
    verify_successor,
)


def _packet() -> dict[str, object]:
    records = [
        {
            "domain": "customer",
            "source_id": f"cus_{number:03d}",
            "original_assertion": "create",
            "runtime_result": "NOT_APPLICABLE",
            "successor_assertion": "CREATE_NEW",
        }
        for number in range(503)
    ]
    value: dict[str, object] = {
        "contract": "hcp-current-overlay-merge-packet/v3",
        "preview_baseline_sha256": EXPECTED["baseline_file"],
        "records": records,
    }
    value["digest"] = semantic_digest(value)
    return value


def test_successor_requires_exact_503_record_coverage_and_stable_digest() -> None:
    packet = _packet()
    verify_successor(packet)
    assert packet["digest"] == semantic_digest(packet)


def test_duplicate_assertion_is_rejected() -> None:
    packet = _packet()
    packet["records"][1] = copy.deepcopy(packet["records"][0])  # type: ignore[index]
    packet["digest"] = semantic_digest(packet)
    with pytest.raises(ValueError, match="duplicate"):
        verify_successor(packet)


def test_baseline_digest_mismatch_is_rejected() -> None:
    packet = _packet()
    packet["preview_baseline_sha256"] = "0" * 64
    packet["digest"] = semantic_digest(packet)
    with pytest.raises(ValueError, match="baseline binding"):
        verify_successor(packet)


def test_implicit_update_fallback_is_rejected() -> None:
    packet = _packet()
    packet["records"][0]["successor_assertion"] = "UPDATE_OR_CREATE"  # type: ignore[index]
    packet["digest"] = semantic_digest(packet)
    with pytest.raises(ValueError, match="unsupported"):
        verify_successor(packet)
