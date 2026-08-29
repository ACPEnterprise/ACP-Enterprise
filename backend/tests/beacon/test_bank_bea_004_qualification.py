from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.beacon.contracts import BeaconSeverity
from app.beacon.evaluation import SignalEvaluationService
from app.beacon.operational_prioritization import (
    RANKING_VERSION,
    URGENCY_POLICIES,
    OperationalSignalPrioritizer,
)
from tests.beacon.test_beacon import COMPANY_ID, snapshot

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "docs/architecture/beacon/bank-bea-004-qualification.v1.json"
NOW = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evidence() -> dict[str, object]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def operational_signals():
    return tuple(
        signal
        for signal in SignalEvaluationService().evaluate_signals(snapshot())
        if signal.evidence_quality is not None
    )


def prioritize(signals):
    return OperationalSignalPrioritizer().prioritize(
        tuple(signals),
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        evaluated_at=NOW,
    )


def contract_payload() -> dict[str, object]:
    return {
        "ranking_version": RANKING_VERSION,
        "dimensions": [
            "declared_signal_severity_desc",
            "catalog_priority_band_desc",
            "approved_operational_urgency_desc",
            "stable_signal_uuid_asc",
        ],
        "urgency_policies": [
            {
                "definition_id": definition_id,
                "policy_id": policy.policy_id,
                "version": policy.version,
                "fact_name": policy.fact_name,
                "unit": policy.unit,
            }
            for definition_id, policy in sorted(URGENCY_POLICIES.items())
        ],
    }


def test_qualification_binds_canonical_prioritization_contract() -> None:
    payload = evidence()
    assert payload["implementation_sha"] == (
        "2a6a83c9a6a7e20ab9ce5af7964ed27ae28e27d0"
    )
    assert payload["contract_digest"] == digest(contract_payload())
    unsigned = dict(payload)
    unsigned.pop("qualification_fingerprint")
    assert payload["qualification_fingerprint"] == digest(unsigned)


def test_priority_and_tie_break_are_deterministic_and_explainable() -> None:
    scheduling, jobs = operational_signals()
    tied_scheduling = replace(
        scheduling,
        id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    first = prioritize((jobs, scheduling, tied_scheduling))
    replay = prioritize((tied_scheduling, scheduling, jobs))

    assert [item.signal.id for item in first.items] == [
        item.signal.id for item in replay.items
    ]
    assert first.ranking_digest == replay.ranking_digest
    assert first.items[0].signal.severity is BeaconSeverity.CRITICAL
    assert all(item.ranking.ranking_reason for item in first.items)
    assert first.items[0].ranking.tie_break_identity == tied_scheduling.id
    assert first.items[1].ranking.tie_break_identity == scheduling.id


def test_changed_authoritative_ordering_fact_changes_digest() -> None:
    scheduling, jobs = operational_signals()
    first = prioritize((scheduling, jobs))
    changed = replace(
        jobs,
        supporting_facts=tuple(
            replace(item, value=48) if item.name == "oldest_pause_hours" else item
            for item in jobs.supporting_facts
        ),
    )
    second = prioritize((scheduling, changed))

    assert first.ranking_digest != second.ranking_digest


def test_scope_is_digest_bound_without_cross_company_ranking() -> None:
    signals = operational_signals()
    company_queue = prioritize(signals)
    other_scope = OperationalSignalPrioritizer().prioritize(
        (),
        company_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        branch_id=None,
        evaluated_at=NOW,
    )

    assert company_queue.company_id == COMPANY_ID
    assert company_queue.branch_id == BRANCH_ID
    assert other_scope.items == ()
    assert company_queue.ranking_digest != other_scope.ranking_digest


def test_qualification_preserves_non_autonomous_successor_gate() -> None:
    payload = evidence()
    assert payload["autonomous_action"] == "PROHIBITED"
    assert payload["successor_gate"] == {
        "milestone_id": "BANK.BEA.005",
        "state": "BLOCKED_PENDING_BANK_BEA_004_OWNER_ACCEPTANCE",
    }
