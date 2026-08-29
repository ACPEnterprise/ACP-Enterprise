from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.beacon.catalog import (
    OPERATIONAL_SIGNAL_CATALOG,
    OperationalSignalAdmission,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QUALIFICATION_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "architecture"
    / "beacon"
    / "bank-bea-001-qualification.v1.json"
)


def qualification() -> dict[str, object]:
    return json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))


def fingerprint(payload: dict[str, object]) -> str:
    canonical = dict(payload)
    canonical.pop("qualification_fingerprint", None)
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_qualification_binds_authoritative_catalog_without_accepting_it() -> None:
    evidence = qualification()

    assert evidence["milestone_id"] == "BANK.BEA.001"
    assert evidence["state"] == "QUALIFIED_AWAITING_OWNER_ACCEPTANCE"
    assert evidence["implementation_sha"] == (
        "0f6559ecddb7ca3854c79ea7b5cb31432318976a"
    )
    assert evidence["catalog_id"] == OPERATIONAL_SIGNAL_CATALOG.catalog_id
    assert evidence["catalog_version"] == OPERATIONAL_SIGNAL_CATALOG.version
    assert evidence["catalog_digest"] == OPERATIONAL_SIGNAL_CATALOG.catalog_digest
    assert evidence["definition_count"] == len(OPERATIONAL_SIGNAL_CATALOG.definitions)
    assert evidence["qualification_fingerprint"] == fingerprint(evidence)


def test_qualification_preserves_fail_closed_adapter_and_policy_boundaries() -> None:
    admitted = tuple(
        item
        for item in OPERATIONAL_SIGNAL_CATALOG.definitions
        if item.admission is OperationalSignalAdmission.EVALUATED
    )
    rendered = json.dumps(
        [item.payload() for item in OPERATIONAL_SIGNAL_CATALOG.definitions],
        sort_keys=True,
    ).lower()

    assert len(admitted) == 2
    assert all(item.evaluator_rule_code for item in admitted)
    assert all(
        term not in rendered
        for term in (
            "profitability",
            "margin",
            "autonomous",
            "worker scheduling",
            "production deployment",
        )
    )


def test_successor_remains_owner_gated() -> None:
    evidence = qualification()

    assert evidence["successor_gate"] == {
        "milestone_id": "BANK.BEA.002",
        "state": "BLOCKED_PENDING_BANK_BEA_001_OWNER_ACCEPTANCE",
    }
    assert "owner acceptance" in evidence["excluded_authority"]
