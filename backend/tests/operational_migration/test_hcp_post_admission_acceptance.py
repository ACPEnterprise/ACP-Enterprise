from dataclasses import replace

import pytest

from app.operational_migration.hcp_post_admission_acceptance import (
    CONTRACT,
    AcceptancePlan,
    ClassifiedRecord,
    WriteClassification,
    _build_plan,
    verify_execution,
    verify_failed_execution,
)


def _plan() -> AcceptancePlan:
    records = (
        ClassifiedRecord(
            domain="customer",
            source_id="customer-1",
            assertion="create",
            classification=WriteClassification.SAFE_SUPPORTING_PARENT,
            reason="current_graph_parent",
            source_digest="a" * 64,
            parent_keys=(),
        ),
        ClassifiedRecord(
            domain="appointment",
            source_id="appointment-held",
            assertion="update",
            classification=WriteClassification.HELD,
            reason="historical_update_requires_native_lifecycle_hold",
            source_digest="b" * 64,
            parent_keys=(),
        ),
    )
    return _build_plan(
        overlay_manifest_digest="c" * 64,
        overlay_file_sha256="d" * 64,
        acquired_at="2026-09-12T17:00:00Z",
        cutoff_date="2026-09-12",
        records=records,
        current_source_ids={
            "customer": ("customer-1",),
            "service_location": (),
            "job": (),
            "appointment": (),
        },
    )


def _snapshot() -> dict[str, object]:
    return {
        "mutation_authority": "none",
        "current_records": [
            {
                "domain": "customer",
                "source_id": "customer-1",
                "native_id": "native-1",
                "source_digest": "a" * 64,
                "native_evidence_digest": "e" * 64,
                "company_scope_matches": True,
                "branch_scope_matches": True,
            }
        ],
        "active_held_source_ids": [],
        "orphan_count": 0,
        "lifecycle_regression_count": 0,
        "replay_business_event_delta": 0,
        "technician_hold_count": 0,
        "current_location_gap_count": 0,
        "digest": "f" * 64,
    }


def _receipt() -> dict[str, object]:
    return {
        "manifest_digest": "c" * 64,
        "digest": "1" * 64,
        "journal": [
            {
                "key": {"domain": "customer", "source_id": "customer-1"},
                "outcome": "created",
                "native_id": "native-1",
            },
            {
                "key": {
                    "domain": "appointment",
                    "source_id": "appointment-held",
                },
                "outcome": "held",
                "native_id": None,
            },
        ],
    }


def test_accepts_complete_receipt_snapshot_and_identical_replay() -> None:
    receipt = _receipt()
    result = verify_execution(
        _plan(), receipt=receipt, snapshot=_snapshot(), replay_receipt=receipt
    )
    assert result["status"] == "ACCEPTED"
    assert result["counts"] == {"created": 1, "held": 1}


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda receipt, snapshot: receipt["journal"].pop(), "source identity"),
        (
            lambda receipt, snapshot: snapshot.update(active_held_source_ids=["x"]),
            "held source identity",
        ),
        (
            lambda receipt, snapshot: snapshot.update(replay_business_event_delta=1),
            "duplicated Business Events",
        ),
    ],
)
def test_fails_closed_on_incomplete_or_unsafe_evidence(mutation, match) -> None:
    receipt, snapshot = _receipt(), _snapshot()
    mutation(receipt, snapshot)
    with pytest.raises(ValueError, match=match):
        verify_execution(_plan(), receipt=receipt, snapshot=snapshot)


def test_plan_digest_detects_tampering() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(plan, cutoff_date="2026-09-13").verify()


def test_failed_execution_requires_atomic_rollback_evidence() -> None:
    evidence = {
        "state": "failure",
        "transaction_rolled_back": True,
        "before_native_digest": "same",
        "after_native_digest": "same",
        "before_event_digest": "events",
        "after_event_digest": "events",
        "success_receipt_persisted": False,
        "restore_receipt_digest": "a" * 64,
    }
    assert verify_failed_execution(evidence)["status"] == (
        "FAILED_EXECUTION_SAFELY_RECONCILED"
    )
    evidence["after_native_digest"] = "changed"
    with pytest.raises(ValueError, match="atomic rollback"):
        verify_failed_execution(evidence)


def test_contract_is_versioned() -> None:
    assert CONTRACT == "hcp-current-overlay-post-admission-acceptance/v1"
