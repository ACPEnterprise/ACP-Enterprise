from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.beacon.catalog import OPERATIONAL_SIGNAL_CATALOG
from app.beacon.evidence_evaluation import (
    EVIDENCE_EVALUATION_REGISTRY,
    EvaluationReadiness,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QUALIFICATION_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "architecture"
    / "beacon"
    / "bank-bea-002-qualification.v1.json"
)


def qualification() -> dict[str, object]:
    return json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))


def digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def registry_payload() -> list[dict[str, object]]:
    return [
        {
            "definition_id": item.definition_id,
            "family": item.family.value,
            "readiness": item.readiness.value,
            "authoritative_source_contract": item.authoritative_source_contract,
            "required_fact_contract": item.required_fact_contract,
            "adapter_code": item.adapter_code,
            "evaluator_code": item.evaluator_code,
            "blocker": item.blocker,
            "limitations": item.limitations,
        }
        for item in EVIDENCE_EVALUATION_REGISTRY.registrations
    ]


def test_qualification_binds_canonical_registry_and_implementation() -> None:
    evidence = qualification()

    assert evidence["state"] == "QUALIFIED_AWAITING_OWNER_ACCEPTANCE"
    assert evidence["implementation_sha"] == (
        "e82e19bdc012d60f663fed012bc5797175abde98"
    )
    assert evidence["catalog_id"] == OPERATIONAL_SIGNAL_CATALOG.catalog_id
    assert evidence["catalog_digest"] == OPERATIONAL_SIGNAL_CATALOG.catalog_digest
    assert evidence["definition_count"] == len(
        EVIDENCE_EVALUATION_REGISTRY.registrations
    )
    assert evidence["registry_digest"] == digest(registry_payload())

    fingerprint_payload = dict(evidence)
    fingerprint_payload.pop("qualification_fingerprint")
    assert evidence["qualification_fingerprint"] == digest(fingerprint_payload)


def test_qualification_preserves_fail_closed_readiness_distribution() -> None:
    evidence = qualification()
    counts = {
        readiness.value: sum(
            item.readiness is readiness
            for item in EVIDENCE_EVALUATION_REGISTRY.registrations
        )
        for readiness in EvaluationReadiness
    }

    assert evidence["readiness_counts"] == counts
    assert counts == {
        "evaluable": 2,
        "partially_evaluable": 16,
        "not_evaluable": 3,
        "conflicting": 0,
    }
    assert all(
        item.evaluator_implemented and item.blocker is None
        if item.readiness is EvaluationReadiness.EVALUABLE
        else not item.evaluator_implemented and bool(item.blocker)
        for item in EVIDENCE_EVALUATION_REGISTRY.registrations
    )


def test_qualification_keeps_successor_and_external_authority_gated() -> None:
    evidence = qualification()

    assert evidence["successor_gate"] == {
        "milestone_id": "BANK.BEA.003",
        "state": "BLOCKED_PENDING_BANK_BEA_002_OWNER_ACCEPTANCE",
    }
    exclusions = set(evidence["excluded_authority"])
    assert "QBO or HCP source promotion" in exclusions
    assert "AI or autonomous action" in exclusions
    assert "Preview or Production" in exclusions
