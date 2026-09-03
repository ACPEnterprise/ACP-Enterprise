from datetime import datetime, timedelta, timezone

import pytest
from app.engineering_control.scheduler.headless import (
    ApprovedQueueItem,
    ExecutionObservation,
    propose_headless_capacity,
)
from app.engineering_control.scheduler.readiness import (
    load_current_readiness_projection,
)


def _executable_ids() -> tuple[str, ...]:
    return load_current_readiness_projection().executable_milestone_ids


def test_owner_approved_queue_activates_only_executable_free_capacity() -> None:
    readiness = load_current_readiness_projection()
    first, second = _executable_ids()[:2]
    plan = propose_headless_capacity(
        readiness,
        [ApprovedQueueItem(milestone_id=first, capacity_identity="OM1")],
        [
            ExecutionObservation(
                milestone_id=second, capacity_identity="OM2", state="queued"
            )
        ],
        {},
        now=datetime.now(timezone.utc),
    )
    assert [(item.kind, item.milestone_id) for item in plan.proposals] == [
        ("activate", first)
    ]
    assert plan.authority_fingerprint == readiness.fingerprint


def test_completed_item_refills_only_to_approved_executable_successor() -> None:
    readiness = load_current_readiness_projection()
    predecessor, successor = _executable_ids()[:2]
    plan = propose_headless_capacity(
        readiness,
        [ApprovedQueueItem(milestone_id=successor, capacity_identity="MIG")],
        [
            ExecutionObservation(
                milestone_id=predecessor,
                capacity_identity="MIG",
                state="completed",
            )
        ],
        {predecessor: [successor]},
        now=datetime.now(timezone.utc),
    )
    assert [(item.kind, item.milestone_id) for item in plan.proposals] == [
        ("refill", successor)
    ]


def test_stale_execution_is_quarantined_for_reconciliation_without_retry() -> None:
    readiness = load_current_readiness_projection()
    stale, queued = _executable_ids()[:2]
    now = datetime.now(timezone.utc)
    plan = propose_headless_capacity(
        readiness,
        [ApprovedQueueItem(milestone_id=queued, capacity_identity="OM1")],
        [
            ExecutionObservation(
                milestone_id=stale,
                capacity_identity="OM1",
                state="running",
                heartbeat_at=now - timedelta(minutes=6),
            )
        ],
        {},
        now=now,
        stale_after_seconds=300,
    )
    assert [item.kind for item in plan.proposals] == ["reconcile"]
    assert plan.blocked == (f"{queued}:capacity_occupied:OM1",)


def test_unknown_duplicate_and_non_executable_authority_fail_closed() -> None:
    readiness = load_current_readiness_projection()
    executable = _executable_ids()[0]
    duplicate = ApprovedQueueItem(milestone_id=executable, capacity_identity="OM1")
    with pytest.raises(ValueError, match="duplicate"):
        propose_headless_capacity(
            readiness, [duplicate, duplicate], [], {}, now=datetime.now(timezone.utc)
        )
    with pytest.raises(ValueError, match="unknown"):
        propose_headless_capacity(
            readiness,
            [ApprovedQueueItem(milestone_id="BANK.NOPE.999", capacity_identity="OM1")],
            [],
            {},
            now=datetime.now(timezone.utc),
        )

    blocked = next(
        item for item in readiness.milestones if item.current_state != "EXECUTABLE"
    )
    plan = propose_headless_capacity(
        readiness,
        [ApprovedQueueItem(milestone_id=blocked.milestone_id, capacity_identity="OM1")],
        [],
        {},
        now=datetime.now(timezone.utc),
    )
    assert not plan.proposals
    assert plan.blocked == (f"{blocked.milestone_id}:{blocked.current_state}",)
