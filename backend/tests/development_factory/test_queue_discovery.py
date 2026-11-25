from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from development_factory.queue_discovery import (
    DiscoveryLimits,
    GitQueueSource,
    QueueCandidate,
    QueueDiscoveryError,
    QueueDiscoverySupervisor,
    QueueNetworkError,
)

OLD_SHA = "1" * 40
NEW_SHA = "2" * 40
NEW_HEAD = "3" * 40
EVIDENCE = "a" * 64


def payload(*, include_follow_on: bool = False) -> dict[str, object]:
    assignments: list[dict[str, object]] = [
        {
            "id": "OM1-FIRST",
            "lane": "OM1",
            "priority": "P1",
            "state": "READY_AFTER_INVENTORY",
            "depends_on": [],
            "objective": "First bounded task.",
            "allowed_paths": ["backend/development_factory/**"],
            "validation": ["focused tests"],
            "stop_conditions": ["deployment"],
        },
        {
            "id": "OM1-DEPENDENT",
            "lane": "OM1",
            "priority": "P1",
            "state": "BLOCKED_DEPENDENCY",
            "depends_on": ["OM1-FIRST"],
            "objective": "Dependent bounded task.",
            "allowed_paths": ["backend/tests/**"],
            "validation": ["focused tests"],
            "stop_conditions": ["deployment"],
        },
        {
            "id": "OM2-OTHER",
            "lane": "OM2",
            "priority": "P1",
            "state": "READY_AFTER_INVENTORY",
            "depends_on": [],
            "objective": "Other machine task.",
        },
    ]
    if include_follow_on:
        assignments.append(
            {
                "id": "OM1-NEW-QUEUE",
                "lane": "OM1",
                "priority": "P1",
                "state": "READY_AFTER_INVENTORY",
                "depends_on": [],
                "objective": "Newly published task.",
            }
        )
    return {
        "schema_version": "twelfthats.continuous-engineering-queue.v1",
        "status": "PREPARED_PENDING_MACHINE_ACTIVATION",
        "assignments": assignments,
        "manual_reservations": [
            {
                "assignment_id": item["id"],
                "machine": item["lane"],
                "execution_identity": ("OM1-A" if item["lane"] == "OM1" else "OM2-A"),
                "owner": "LAPTOP_MASTER",
                "status": "RESERVED_MANUAL",
                "automated_claims_blocked": True,
                "reason": "Bounded manual recovery.",
            }
            for item in assignments
        ],
        "completed_evidence": [],
    }


def candidate(
    commit: str,
    value: dict[str, object],
    *,
    ref: str = "refs/heads/handoff/continuous-engineering-queue",
) -> QueueCandidate:
    return QueueCandidate(ref, commit, commit, value)


class Source:
    def __init__(
        self,
        candidates: tuple[QueueCandidate, ...],
        *,
        failures: int = 0,
        ancestry: set[tuple[str, str]] | None = None,
    ) -> None:
        self.candidates = candidates
        self.failures = failures
        self.calls = 0
        self.ancestry = ancestry or set()

    def load(self) -> tuple[QueueCandidate, ...]:
        self.calls += 1
        if self.calls <= self.failures:
            raise QueueNetworkError("simulated interruption")
        return self.candidates

    def is_ancestor(self, older: str, newer: str) -> bool:
        return older == newer or (older, newer) in self.ancestry


def supervisor(tmp_path: Path, **changes: object) -> QueueDiscoverySupervisor:
    max_attempts = changes.get("max_attempts", 3)
    max_candidates = changes.get("max_queue_candidates", 128)
    assert isinstance(max_attempts, int)
    assert isinstance(max_candidates, int)
    limits = DiscoveryLimits(
        max_attempts=max_attempts,
        base_retry_seconds=0,
        max_retry_seconds=0,
        max_queue_candidates=max_candidates,
    )
    return QueueDiscoverySupervisor(
        tmp_path / "coordination-state.json",
        limits=limits,
        sleep=lambda _: None,
    )


def test_discovers_new_queue_without_branch_keyword_filter(tmp_path: Path) -> None:
    new = candidate(
        NEW_SHA,
        payload(include_follow_on=True),
        ref="refs/heads/handoff/overnight-follow-on-queue-67bbd83d",
    )

    result = supervisor(tmp_path).discover(Source((new,)), machine="OM1")

    assert result.queue_commit_sha == NEW_SHA
    assert result.eligible_assignments == ("OM1-FIRST", "OM1-NEW-QUEUE")


def test_queue_supersession_replaces_stale_reference(tmp_path: Path) -> None:
    old = candidate(OLD_SHA, payload())
    new = candidate(
        NEW_SHA,
        payload(include_follow_on=True),
        ref="refs/heads/handoff/overnight-follow-on",
    )
    control = supervisor(tmp_path)
    control.discover(Source((old,)), machine="OM1")

    result = control.discover(
        Source((old, new), ancestry={(OLD_SHA, NEW_SHA)}),
        machine="OM1",
    )

    assert result.queue_commit_sha == NEW_SHA
    assert "OM1-NEW-QUEUE" in result.eligible_assignments


def test_rejects_stale_or_ambiguous_queue_after_checkpoint(tmp_path: Path) -> None:
    control = supervisor(tmp_path)
    control.discover(Source((candidate(NEW_SHA, payload()),)), machine="OM1")

    with pytest.raises(QueueDiscoveryError, match="does not descend"):
        control.discover(Source((candidate(OLD_SHA, payload()),)), machine="OM1")

    with pytest.raises(QueueDiscoveryError, match="ambiguous"):
        supervisor(tmp_path / "other").discover(
            Source(
                (
                    candidate(OLD_SHA, payload()),
                    candidate(
                        NEW_SHA,
                        payload(include_follow_on=True),
                        ref="refs/heads/handoff/other-queue",
                    ),
                )
            ),
            machine="OM1",
        )


def test_network_interruption_retries_with_bound_and_recovers(tmp_path: Path) -> None:
    source = Source((candidate(NEW_SHA, payload()),), failures=2)
    result = supervisor(tmp_path).discover(source, machine="OM1")
    assert result.attempts == 3
    assert source.calls == 3

    blocked = Source((candidate(NEW_SHA, payload()),), failures=3)
    with pytest.raises(QueueDiscoveryError, match="retry budget exhausted"):
        supervisor(tmp_path / "blocked").discover(blocked, machine="OM1")
    assert blocked.calls == 3


def test_restart_requires_reconciliation_and_prevents_duplicate_execution(
    tmp_path: Path,
) -> None:
    control = supervisor(tmp_path)
    result = control.discover(Source((candidate(NEW_SHA, payload()),)), machine="OM1")
    control.begin("OM1-FIRST", queue_digest=result.queue_digest, machine="OM1")
    with pytest.raises(QueueDiscoveryError, match="not ready"):
        control.begin("OM1-FIRST", queue_digest=result.queue_digest, machine="OM1")

    restarted = supervisor(tmp_path)
    assert restarted.recover_after_restart(machine="OM1") == ("OM1-FIRST",)
    after_restart = restarted.discover(
        Source((candidate(NEW_SHA, payload()),)), machine="OM1"
    )
    assert "OM1-FIRST" not in after_restart.eligible_assignments
    restarted.reconcile(
        "OM1-FIRST",
        completed=False,
        evidence_sha256=EVIDENCE,
        machine="OM1",
    )
    ready = restarted.discover(Source((candidate(NEW_SHA, payload()),)), machine="OM1")
    assert "OM1-FIRST" in ready.eligible_assignments


def test_completed_recognition_and_dependency_clearance(tmp_path: Path) -> None:
    value = payload()
    value["completed_evidence"] = [
        {
            "assignment_id": "OM1-FIRST",
            "commit_sha": "f" * 40,
            "remote_ref": "refs/heads/work/om1-first",
            "evidence": "qualified",
        }
    ]

    result = supervisor(tmp_path).discover(
        Source((candidate(NEW_SHA, value),)), machine="OM1"
    )

    assert result.completed_assignments == ("OM1-FIRST",)
    assert result.eligible_assignments == ("OM1-DEPENDENT",)


def test_machine_ownership_and_manual_claim_exclusion(tmp_path: Path) -> None:
    source = Source((candidate(NEW_SHA, payload()),))
    assert supervisor(tmp_path / "om1").discover(
        source, machine="OM1"
    ).eligible_assignments == ("OM1-FIRST",)
    assert supervisor(tmp_path / "om2").discover(
        Source((candidate(NEW_SHA, payload()),)), machine="OM2"
    ).eligible_assignments == ("OM2-OTHER",)


def test_shared_checkpoint_fences_machine_lifecycle_operations(
    tmp_path: Path,
) -> None:
    control = supervisor(tmp_path)
    source = Source((candidate(NEW_SHA, payload()),))
    om1 = control.discover(source, machine="OM1")
    om2 = control.discover(Source((candidate(NEW_SHA, payload()),)), machine="OM2")

    with pytest.raises(QueueDiscoveryError, match="another machine"):
        control.begin("OM1-FIRST", queue_digest=om1.queue_digest, machine="OM2")
    control.begin("OM1-FIRST", queue_digest=om1.queue_digest, machine="OM1")
    control.begin("OM2-OTHER", queue_digest=om2.queue_digest, machine="OM2")

    restarted = supervisor(tmp_path)
    assert restarted.recover_after_restart(machine="OM1") == ("OM1-FIRST",)
    assert restarted.recover_after_restart(machine="OM2") == ("OM2-OTHER",)
    with pytest.raises(QueueDiscoveryError, match="another machine"):
        restarted.reconcile(
            "OM1-FIRST",
            completed=False,
            evidence_sha256=EVIDENCE,
            machine="OM2",
        )


def test_local_completion_clears_dependencies_and_prevents_duplicate_execution(
    tmp_path: Path,
) -> None:
    control = supervisor(tmp_path)
    source = Source((candidate(NEW_SHA, payload()),))
    first = control.discover(source, machine="OM1")
    control.begin("OM1-FIRST", queue_digest=first.queue_digest, machine="OM1")
    control.complete("OM1-FIRST", evidence_sha256=EVIDENCE, machine="OM1")

    follow_on = control.discover(
        Source((candidate(NEW_SHA, payload()),)), machine="OM1"
    )
    assert follow_on.completed_assignments == ("OM1-FIRST",)
    assert follow_on.eligible_assignments == ("OM1-DEPENDENT",)
    with pytest.raises(QueueDiscoveryError, match="not ready"):
        control.begin("OM1-FIRST", queue_digest=first.queue_digest, machine="OM1")

    control.begin("OM1-DEPENDENT", queue_digest=follow_on.queue_digest, machine="OM1")
    control.complete("OM1-DEPENDENT", evidence_sha256="b" * 64, machine="OM1")
    exhausted = control.discover(
        Source((candidate(NEW_SHA, payload()),)), machine="OM1"
    )
    assert exhausted.eligible_assignments == ()


def test_queue_supersession_cannot_move_a_running_assignment_between_machines(
    tmp_path: Path,
) -> None:
    control = supervisor(tmp_path)
    original = payload()
    first = control.discover(Source((candidate(OLD_SHA, original),)), machine="OM1")
    control.begin("OM1-FIRST", queue_digest=first.queue_digest, machine="OM1")
    successor = json.loads(json.dumps(original))
    successor["assignments"][0]["lane"] = "OM2"
    successor["manual_reservations"][0]["machine"] = "OM2"

    with pytest.raises(QueueDiscoveryError, match="machine ownership changed"):
        control.discover(
            Source(
                (candidate(NEW_SHA, successor),),
                ancestry={(OLD_SHA, NEW_SHA)},
            ),
            machine="OM2",
        )


def test_checkpoint_integrity_and_safe_shutdown(tmp_path: Path) -> None:
    control = supervisor(tmp_path)
    result = control.discover(Source((candidate(NEW_SHA, payload()),)), machine="OM1")
    control.begin("OM1-FIRST", queue_digest=result.queue_digest, machine="OM1")
    assert control.safe_shutdown(machine="OM1") == ("OM1-FIRST",)

    state_path = tmp_path / "coordination-state.json"
    state = json.loads(state_path.read_text())
    state["assignment_states"]["OM1-FIRST"] = "completed"
    state_path.write_text(json.dumps(state))
    with pytest.raises(QueueDiscoveryError, match="integrity failed"):
        control.recover_after_restart(machine="OM1")


def test_resource_limits_fail_closed(tmp_path: Path) -> None:
    first = candidate(OLD_SHA, payload())
    second = replace(
        candidate(NEW_SHA, payload(include_follow_on=True)),
        ref="refs/heads/handoff/second",
    )
    with pytest.raises(QueueDiscoveryError, match="candidate limit"):
        supervisor(tmp_path, max_queue_candidates=1).discover(
            Source((first, second), ancestry={(OLD_SHA, NEW_SHA)}),
            machine="OM1",
        )


def test_network_failure_checkpoint_never_persists_secret_text(tmp_path: Path) -> None:
    class SecretFailureSource(Source):
        def load(self) -> tuple[QueueCandidate, ...]:
            raise QueueNetworkError("token=not-a-real-secret-for-testing")

    control = supervisor(tmp_path, max_attempts=1)
    with pytest.raises(QueueDiscoveryError, match="retry budget exhausted"):
        control.discover(SecretFailureSource(()), machine="OM1")

    checkpoint = (tmp_path / "coordination-state.json").read_text()
    assert "not-a-real-secret-for-testing" not in checkpoint
    assert "token=" not in checkpoint


def test_git_source_contract_scans_all_handoff_refs() -> None:
    source = GitQueueSource(Path.cwd())
    assert source.remote == "origin"
    assert source.limits.max_remote_refs >= source.limits.max_queue_candidates
