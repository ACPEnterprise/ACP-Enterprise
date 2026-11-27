from __future__ import annotations

import copy
import hashlib
import json
import stat
from pathlib import Path

import pytest
from development_factory.coordination import validate_queue
from development_factory.queue_discovery import (
    QueueCandidate,
    QueueDiscoverySupervisor,
    assignment_contract_digest,
)
from development_factory.unattended_supervisor import (
    PersistentSupervisor,
    ResourceSnapshot,
    SupervisorLimits,
    UnattendedSupervisorError,
)

AUTHORITY_REF = "refs/heads/handoff/continuous-engineering-authority-20261125"
QUEUE_SHA = "a" * 40
NEXT_QUEUE_SHA = "c" * 40


class Source:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def load(self) -> tuple[QueueCandidate, ...]:
        return (QueueCandidate(AUTHORITY_REF, QUEUE_SHA, QUEUE_SHA, self.payload),)

    def is_ancestor(self, older: str, newer: str) -> bool:
        return older == newer


class ReplenishingSource:
    def __init__(
        self, initial: dict[str, object], successor: dict[str, object]
    ) -> None:
        self.payloads = (initial, successor)
        self.calls = 0

    def load(self) -> tuple[QueueCandidate, ...]:
        index = min(self.calls, 1)
        self.calls += 1
        commit = QUEUE_SHA if index == 0 else NEXT_QUEUE_SHA
        return (QueueCandidate(AUTHORITY_REF, commit, commit, self.payloads[index]),)

    def is_ancestor(self, older: str, newer: str) -> bool:
        return older == newer or (older, newer) == (QUEUE_SHA, NEXT_QUEUE_SHA)


class FailingExecutor:
    calls = 0

    def execute(self, assignment, reservation, entry, context):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise RuntimeError("simulated bounded execution failure")


def payload() -> dict[str, object]:
    return {
        "schema_version": "twelfthats.continuous-engineering-queue.v1",
        "status": "AUTHORITATIVE_HANDOFF_PENDING_MACHINE_ACKNOWLEDGMENT",
        "assignments": [
            {
                "id": "OM1-DF-SUPERVISOR-CONTINUATION-03",
                "lane": "OM1",
                "priority": "P1",
                "state": "READY_AFTER_INVENTORY",
                "depends_on": [],
                "objective": "Previously completed supervisor work.",
                "allowed_paths": ["backend/development_factory/**"],
                "validation": ["completion evidence"],
                "stop_conditions": ["duplicate execution"],
            },
            {
                "id": "OM1-DF-SUPERVISOR-CONTINUATION-04",
                "lane": "OM1",
                "priority": "P1",
                "state": "READY_AFTER_INVENTORY",
                "depends_on": ["OM1-DF-SUPERVISOR-CONTINUATION-03"],
                "objective": "Operate the persistent identity-bound supervisor.",
                "allowed_paths": ["backend/development_factory/**"],
                "validation": ["current authority discovery"],
                "stop_conditions": ["automatic protected execution"],
            },
            {
                "id": "OM1-DF-SUPERVISOR-UNATTENDED-05",
                "lane": "OM1",
                "priority": "P1",
                "state": "READY_AFTER_INVENTORY",
                "depends_on": ["OM1-DF-SUPERVISOR-CONTINUATION-04"],
                "objective": "Qualify a restarted unattended supervisor.",
                "allowed_paths": ["backend/development_factory/**"],
                "validation": ["restart recovery"],
                "stop_conditions": ["unbounded execution"],
            },
        ],
        "manual_reservations": [
            {
                "assignment_id": assignment_id,
                "machine": "OM1",
                "execution_identity": "OM1-B",
                "owner": "LAPTOP_MASTER",
                "status": "RESERVED_MANUAL",
                "automated_claims_blocked": True,
                "reason": "Explicit bounded OM1-B reservation.",
            }
            for assignment_id in (
                "OM1-DF-SUPERVISOR-CONTINUATION-04",
                "OM1-DF-SUPERVISOR-UNATTENDED-05",
            )
        ],
        "completed_evidence": [
            {
                "assignment_id": "OM1-DF-SUPERVISOR-CONTINUATION-03",
                "commit_sha": "b" * 40,
            }
        ],
    }


def write_plan(tmp_path: Path, value: dict[str, object]) -> Path:
    queue = validate_queue(value)
    entries = []
    for assignment_id, profile in (
        ("OM1-DF-SUPERVISOR-CONTINUATION-04", "supervisor_continuation"),
        ("OM1-DF-SUPERVISOR-UNATTENDED-05", "supervisor_unattended"),
    ):
        entries.append(
            {
                "assignment_id": assignment_id,
                "contract_sha256": assignment_contract_digest(
                    queue.by_id[assignment_id],
                    queue.manual_reservation_by_id[assignment_id],
                ),
                "profile": profile,
            }
        )
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "schema": "twelfthats.unattended-execution-plan.v1",
                "machine": "OM1",
                "execution_identity": "OM1-B",
                "authority_ref": AUTHORITY_REF,
                "authority_sha": QUEUE_SHA,
                "assignments": entries,
                "safety": {
                    "worker_control_claims": False,
                    "worker_control_leases": False,
                    "automatic_commit": False,
                    "automatic_push": False,
                    "automatic_merge": False,
                    "automatic_deploy": False,
                    "protected_execution": False,
                },
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def supervisor(
    tmp_path: Path,
    value: dict[str, object],
    *,
    executor=None,  # type: ignore[no-untyped-def]
) -> PersistentSupervisor:
    return PersistentSupervisor(
        tmp_path,
        discovery=QueueDiscoverySupervisor(tmp_path / "coordination.json"),
        source=Source(value),
        plan_path=write_plan(tmp_path, value),
        runtime_state_path=tmp_path / "runtime.json",
        machine="OM1",
        execution_identity="OM1-B",
        executor=executor,
        sleep=lambda _seconds: None,
        resource_probe=lambda _root: ResourceSnapshot(
            logical_cpu_count=12,
            load_average_1m=1.0,
            free_bytes=20 * 1024**3,
            process_max_rss_bytes=32 * 1024**2,
        ),
    )


def limits(*, max_assignments: int = 1, max_cycles: int = 0) -> SupervisorLimits:
    return SupervisorLimits(
        poll_seconds=1,
        max_cycles=max_cycles,
        max_assignments=max_assignments,
        max_runtime_seconds=60,
        minimum_free_bytes=1024**3,
        maximum_rss_bytes=64 * 1024**2,
    )


def test_successive_assignments_require_restart_and_execute_once(
    tmp_path: Path,
) -> None:
    value = payload()
    control = supervisor(tmp_path, value)

    first = control.run(limits=limits())
    assert first.executed_assignments == ("OM1-DF-SUPERVISOR-CONTINUATION-04",)

    second = control.run(limits=limits())
    assert second.executed_assignments == ("OM1-DF-SUPERVISOR-UNATTENDED-05",)

    third = control.run(limits=limits(max_cycles=1))
    assert third.executed_assignments == ()
    assert third.status == "CYCLE_LIMIT_REACHED"

    runtime = json.loads((tmp_path / "runtime.json").read_text())
    assert runtime["start_count"] == 3
    assert runtime["active_pid"] is None
    assert runtime["last_heartbeat_at_utc"] is not None
    assert runtime["last_observed_authority_sha"] == QUEUE_SHA
    assert {
        assignment_id: record["attempts"]
        for assignment_id, record in runtime["assignments"].items()
    } == {
        "OM1-DF-SUPERVISOR-CONTINUATION-04": 1,
        "OM1-DF-SUPERVISOR-UNATTENDED-05": 1,
    }
    assert stat.S_IMODE((tmp_path / "runtime.json").stat().st_mode) == 0o600
    unattended_evidence = json.loads(
        (tmp_path / "evidence" / "OM1-DF-SUPERVISOR-UNATTENDED-05.json").read_text()
    )
    assert unattended_evidence["operation"]["restart_observed"] is True


def test_stale_active_pid_is_reconciled_under_exclusive_lock(tmp_path: Path) -> None:
    value = payload()
    control = supervisor(tmp_path, value)
    control.run(limits=limits())

    runtime_path = tmp_path / "runtime.json"
    runtime = json.loads(runtime_path.read_text())
    runtime["active_pid"] = 987654
    unsigned = {key: item for key, item in runtime.items() if key != "state_digest"}
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    runtime["state_digest"] = hashlib.sha256(encoded).hexdigest()
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    runtime_path.chmod(0o600)

    control.run(limits=limits())

    reconciled = json.loads(runtime_path.read_text())
    assert reconciled["active_pid"] is None
    assert reconciled["last_stale_pid"] == 987654
    assert reconciled["last_stale_pid_recovered_at_utc"] is not None
    assert any(
        event["event"] == "STALE_ACTIVE_PID_RECOVERED" for event in reconciled["events"]
    )


def test_descendant_authority_replenishes_supported_profile_without_prompt(
    tmp_path: Path,
) -> None:
    initial = payload()
    initial["completed_evidence"].extend(
        [
            {
                "assignment_id": "OM1-DF-SUPERVISOR-CONTINUATION-04",
                "commit_sha": "d" * 40,
            },
            {
                "assignment_id": "OM1-DF-SUPERVISOR-UNATTENDED-05",
                "commit_sha": "e" * 40,
            },
        ]
    )
    successor = copy.deepcopy(initial)
    successor["assignments"].append(
        {
            "id": "OM1-DF-SUPERVISOR-QUALIFICATION-06",
            "lane": "OM1",
            "priority": "P1",
            "state": "READY_AFTER_INVENTORY",
            "depends_on": ["OM1-DF-SUPERVISOR-UNATTENDED-05"],
            "objective": "Qualify descendant authority replenishment.",
            "allowed_paths": ["backend/development_factory/**"],
            "validation": ["successor discovery"],
            "stop_conditions": ["unbounded execution"],
            "execution_profile": "supervisor_continuation",
        }
    )
    successor["manual_reservations"].append(
        {
            "assignment_id": "OM1-DF-SUPERVISOR-QUALIFICATION-06",
            "machine": "OM1",
            "execution_identity": "OM1-B",
            "owner": "LAPTOP_MASTER",
            "status": "RESERVED_MANUAL",
            "automated_claims_blocked": True,
            "reason": "Bounded descendant-authority qualification.",
        }
    )
    plan_path = write_plan(tmp_path, initial)
    plan_payload = json.loads(plan_path.read_text())
    plan_payload["allow_authority_profile_extensions"] = True
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")
    plan_path.chmod(0o600)
    control = PersistentSupervisor(
        tmp_path,
        discovery=QueueDiscoverySupervisor(tmp_path / "coordination.json"),
        source=ReplenishingSource(initial, successor),
        plan_path=plan_path,
        runtime_state_path=tmp_path / "runtime.json",
        machine="OM1",
        execution_identity="OM1-B",
        sleep=lambda _seconds: None,
        resource_probe=lambda _root: ResourceSnapshot(
            12, 1.0, 20 * 1024**3, 32 * 1024**2
        ),
    )

    result = control.run(limits=limits())

    assert result.executed_assignments == ("OM1-DF-SUPERVISOR-QUALIFICATION-06",)
    evidence = json.loads(
        (tmp_path / "evidence" / "OM1-DF-SUPERVISOR-QUALIFICATION-06.json").read_text()
    )
    assert evidence["authority"]["queue_commit_sha"] == NEXT_QUEUE_SHA


def test_execution_plan_supersession_requires_previous_digest(tmp_path: Path) -> None:
    value = payload()
    control = supervisor(tmp_path, value)
    control.run(limits=limits())
    plan_path = tmp_path / "plan.json"
    previous_digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    plan_payload = json.loads(plan_path.read_text())
    plan_payload["allow_authority_profile_extensions"] = True
    plan_payload["supersedes_plan_sha256"] = previous_digest
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")
    plan_path.chmod(0o600)

    control.run(limits=limits())

    runtime = json.loads((tmp_path / "runtime.json").read_text())
    assert runtime["previous_plan_sha256"] == previous_digest
    assert any(
        event["event"] == "EXECUTION_PLAN_SUPERSEDED" for event in runtime["events"]
    )


def test_execution_plan_change_without_supersession_fails_closed(
    tmp_path: Path,
) -> None:
    value = payload()
    control = supervisor(tmp_path, value)
    control.run(limits=limits())
    plan_path = tmp_path / "plan.json"
    plan_payload = json.loads(plan_path.read_text())
    plan_payload["allow_authority_profile_extensions"] = True
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")
    plan_path.chmod(0o600)

    with pytest.raises(UnattendedSupervisorError, match="supersession is unauthorized"):
        control.run(limits=limits())


def test_failed_execution_requires_reconciliation_and_is_not_replayed(
    tmp_path: Path,
) -> None:
    value = payload()
    executor = FailingExecutor()
    control = supervisor(tmp_path, value, executor=executor)

    with pytest.raises(RuntimeError, match="simulated bounded"):
        control.run(limits=limits())
    recovered = control.run(limits=limits())

    assert recovered.status == "RECOVERY_REQUIRED"
    assert recovered.recovered_assignments == ("OM1-DF-SUPERVISOR-CONTINUATION-04",)
    assert executor.calls == 1


def test_plan_contract_change_fails_closed_before_execution(tmp_path: Path) -> None:
    value = payload()
    control = supervisor(tmp_path, value)
    changed = value["assignments"][1]
    changed["objective"] = "Unauthorized expanded objective."

    with pytest.raises(UnattendedSupervisorError, match="contract changed"):
        control.run(limits=limits())
