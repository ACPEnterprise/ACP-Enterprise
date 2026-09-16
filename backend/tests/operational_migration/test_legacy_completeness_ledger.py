from __future__ import annotations

import hashlib
import json

import pytest

from app.operational_migration.legacy_completeness_ledger import (
    CONTRACT,
    COUNT_FIELDS,
    FAMILIES,
    LegacyCompletenessLedger,
)


def test_ledger_requires_all_families_and_preserves_unavailable_counts() -> None:
    families = {
        name: {
            "counts": dict.fromkeys(COUNT_FIELDS),
            "native_state_evidence": "UNAVAILABLE_NOT_ZERO",
            "notes": (),
        }
        for name in FAMILIES
    }
    payload = {
        "contract": CONTRACT,
        "families": families,
        "evidence": {"native_binding_snapshot_sha256": "UNAVAILABLE"},
        "invariants": {"unavailable_counts_are_zero": False},
    }
    ledger = LegacyCompletenessLedger(
        **payload,
        digest=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )

    ledger.verify()
    assert ledger.families["customers"]["counts"]["native_admitted"] is None


def test_ledger_rejects_incomplete_family_coverage() -> None:
    ledger = LegacyCompletenessLedger(
        contract=CONTRACT,
        families={},
        evidence={},
        invariants={},
        digest="not-valid",
    )
    with pytest.raises(ValueError):
        ledger.verify()
