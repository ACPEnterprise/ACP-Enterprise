from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from app.beacon.quality import (
    EVIDENCE_QUALITY_SERVICE,
    EvidenceCompletenessState,
    EvidenceConfidenceState,
    EvidenceFreshnessState,
    EvidenceQualityInput,
    EvidenceReconciliationState,
    EvidenceTemporalBasis,
)

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "docs/architecture/beacon/bank-bea-003-qualification.v1.json"
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evidence() -> dict[str, object]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def quality_input() -> EvidenceQualityInput:
    return EvidenceQualityInput(
        definition_id="operational.scheduling.appointment_overdue",
        source_authority="accepted ACP operational records",
        evidence_identities=("event:b", "event:a"),
        effective_at=NOW,
        observed_as_of=NOW,
        evaluated_at=NOW,
        completeness=EvidenceCompletenessState.COMPLETE,
        reconciliation=EvidenceReconciliationState.RECONCILED,
        evidence_digest="a" * 64,
    )


def semantics_payload() -> list[dict[str, object]]:
    return [
        {
            "definition_id": item.definition_id,
            "readiness": item.readiness.value,
            "confidence": item.confidence_semantics_available,
            "freshness": item.freshness_semantics_available,
            "policy_id": item.freshness_policy_id,
            "policy_version": item.freshness_policy_version,
            "policy_source": item.policy_source,
            "blocker": item.blocker,
        }
        for item in EVIDENCE_QUALITY_SERVICE.semantics()
    ]


def test_qualification_binds_canonical_semantics() -> None:
    payload = evidence()
    assert payload["implementation_sha"] == (
        "cce44ec4227418b7543d05b977b81c9656e21f25"
    )
    assert payload["semantics_digest"] == digest(semantics_payload())
    assert payload["definition_count"] == 21
    assert payload["freshness_policy_count"] == 2
    unsigned = dict(payload)
    unsigned.pop("qualification_fingerprint")
    assert payload["qualification_fingerprint"] == digest(unsigned)


def test_durable_and_deterministic_as_of_evidence_do_not_age() -> None:
    for basis in (
        EvidenceTemporalBasis.DURABLE_EVENT,
        EvidenceTemporalBasis.DETERMINISTIC_AS_OF,
    ):
        result = EVIDENCE_QUALITY_SERVICE.evaluate(
            replace(quality_input(), temporal_basis=basis, observed_as_of=None)
        )
        assert result.freshness is EvidenceFreshnessState.NOT_APPLICABLE
        assert result.confidence is EvidenceConfidenceState.HIGH
        assert result.conclusion_admissible


def test_missing_conflicting_and_reordered_evidence_fail_or_replay_safely() -> None:
    source = quality_input()
    missing = EVIDENCE_QUALITY_SERVICE.evaluate(
        replace(source, observed_as_of=None)
    )
    conflicting = EVIDENCE_QUALITY_SERVICE.evaluate(
        replace(
            source,
            reconciliation=EvidenceReconciliationState.CONFLICTING,
            conflict_identities=("fact:b", "fact:a"),
        )
    )
    first = EVIDENCE_QUALITY_SERVICE.evaluate(source)
    reordered = EVIDENCE_QUALITY_SERVICE.evaluate(
        replace(source, evidence_identities=tuple(reversed(source.evidence_identities)))
    )
    changed = EVIDENCE_QUALITY_SERVICE.evaluate(
        replace(source, evidence_digest="b" * 64)
    )

    assert missing.confidence is EvidenceConfidenceState.UNKNOWN
    assert not missing.conclusion_admissible
    assert conflicting.confidence is EvidenceConfidenceState.CONFLICTING
    assert not conflicting.conclusion_admissible
    assert first == reordered
    assert first.quality_digest != changed.quality_digest


def test_successor_remains_owner_gated() -> None:
    assert evidence()["successor_gate"] == {
        "milestone_id": "BANK.BEA.004",
        "state": "BLOCKED_PENDING_BANK_BEA_003_OWNER_ACCEPTANCE",
    }
