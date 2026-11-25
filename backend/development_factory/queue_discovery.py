"""Durable discovery for Laptop-Master-published coordination queues.

This adapter discovers and projects manual reservations into the existing
coordination contracts. It never issues a Worker Control claim or lease and it
never approves, merges, or deploys work.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from development_factory.coordination import (
    CoordinationError,
    CoordinationQueue,
    canonical_digest,
    validate_queue,
)

STATE_SCHEMA = "twelfthats.coordination-discovery-state.v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
REMOTE_PREFIX = "refs/heads/handoff/"
ELIGIBLE_STATES = frozenset(
    {"READY_AFTER_INVENTORY", "BLOCKED_MACHINE_INVENTORY", "BLOCKED_DEPENDENCY"}
)


class QueueDiscoveryError(ValueError):
    """A fail-closed queue discovery or recovery error."""


class QueueNetworkError(RuntimeError):
    """A transient, secret-free queue transport failure."""


@dataclass(frozen=True)
class DiscoveryLimits:
    max_remote_refs: int = 512
    max_queue_candidates: int = 128
    max_assignments: int = 256
    max_attempts: int = 3
    base_retry_seconds: float = 0.25
    max_retry_seconds: float = 2.0

    def validate(self) -> None:
        if not 1 <= self.max_remote_refs <= 2_048:
            raise QueueDiscoveryError("remote-ref limit is invalid")
        if not 1 <= self.max_queue_candidates <= 512:
            raise QueueDiscoveryError("queue-candidate limit is invalid")
        if not 1 <= self.max_assignments <= 1_024:
            raise QueueDiscoveryError("assignment limit is invalid")
        if not 1 <= self.max_attempts <= 8:
            raise QueueDiscoveryError("retry-attempt limit is invalid")
        if not 0 <= self.base_retry_seconds <= self.max_retry_seconds <= 30:
            raise QueueDiscoveryError("retry-delay limit is invalid")


@dataclass(frozen=True)
class QueueCandidate:
    ref: str
    head_sha: str
    queue_commit_sha: str
    payload: dict[str, object]

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload)


@dataclass(frozen=True)
class DiscoveryResult:
    queue_commit_sha: str
    queue_digest: str
    queue_refs: tuple[str, ...]
    eligible_assignments: tuple[str, ...]
    completed_assignments: tuple[str, ...]
    attempts: int
    status: str


class QueueSource(Protocol):
    def load(self) -> tuple[QueueCandidate, ...]: ...

    def is_ancestor(self, older: str, newer: str) -> bool: ...


class GitQueueSource:
    """Discover every queue-bearing handoff ref without a name keyword filter."""

    def __init__(
        self,
        repo_root: Path,
        *,
        remote: str = "origin",
        limits: DiscoveryLimits | None = None,
    ) -> None:
        self.root = repo_root.resolve()
        self.remote = remote
        self.limits = limits or DiscoveryLimits()
        self.limits.validate()

    def load(self) -> tuple[QueueCandidate, ...]:
        listed = self._run(
            "ls-remote",
            "--heads",
            self.remote,
            f"{REMOTE_PREFIX}*",
            network=True,
        )
        remote_refs: list[tuple[str, str]] = []
        for line in listed.splitlines():
            fields = line.split()
            if len(fields) != 2:
                raise QueueDiscoveryError("remote ref listing is malformed")
            sha, ref = fields
            if not SHA40.fullmatch(sha) or not ref.startswith(REMOTE_PREFIX):
                raise QueueDiscoveryError("remote handoff ref is invalid")
            remote_refs.append((sha, ref))
        if len(remote_refs) > self.limits.max_remote_refs:
            raise QueueDiscoveryError("remote-ref limit exceeded")
        if remote_refs:
            self._run(
                "fetch",
                "--no-tags",
                "--quiet",
                self.remote,
                (f"+{REMOTE_PREFIX}*:refs/coordination-discovery/handoff/*"),
                network=True,
            )

        candidates: list[QueueCandidate] = []
        queue_path = "development-factory/continuous-engineering-queue.v1.json"
        for head_sha, ref in sorted(remote_refs, key=lambda value: value[1]):
            content = self._run_optional("show", f"{head_sha}:{queue_path}")
            if content is None:
                continue
            try:
                payload: object = json.loads(content)
            except json.JSONDecodeError as error:
                raise QueueDiscoveryError("remote queue is not valid JSON") from error
            if not isinstance(payload, dict):
                raise QueueDiscoveryError("remote queue must be an object")
            try:
                validate_queue(payload)
            except CoordinationError as error:
                raise QueueDiscoveryError("remote queue contract is invalid") from error
            queue_commit = self._run(
                "log",
                "-1",
                "--format=%H",
                head_sha,
                "--",
                queue_path,
            )
            if not SHA40.fullmatch(queue_commit):
                raise QueueDiscoveryError("remote queue commit is invalid")
            candidates.append(
                QueueCandidate(
                    ref=ref,
                    head_sha=head_sha,
                    queue_commit_sha=queue_commit,
                    payload=cast(dict[str, object], payload),
                )
            )
        if len(candidates) > self.limits.max_queue_candidates:
            raise QueueDiscoveryError("queue-candidate limit exceeded")
        return tuple(candidates)

    def is_ancestor(self, older: str, newer: str) -> bool:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise QueueDiscoveryError("queue ancestry inspection failed")
        return result.returncode == 0

    def _run(self, *arguments: str, network: bool = False) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            if network:
                raise QueueNetworkError("coordination remote is unavailable")
            raise QueueDiscoveryError("Git coordination inspection failed")
        return result.stdout.strip()

    def _run_optional(self, *arguments: str) -> str | None:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout if result.returncode == 0 else None


class QueueDiscoverySupervisor:
    """Persist discovery, execution fencing, and restart reconciliation state."""

    def __init__(
        self,
        state_path: Path,
        *,
        limits: DiscoveryLimits | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.path = state_path.resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.limits = limits or DiscoveryLimits()
        self.limits.validate()
        self.sleep = sleep

    def discover(
        self,
        source: QueueSource,
        *,
        machine: str,
        supplied_completed: Iterable[str] = (),
        now: datetime | None = None,
    ) -> DiscoveryResult:
        candidates, attempts = self._load_with_retry(source)
        selected, refs = _select_authoritative(candidates, source.is_ancestor)
        queue = validate_queue(selected.payload)
        if len(queue.assignments) > self.limits.max_assignments:
            raise QueueDiscoveryError("assignment limit exceeded")
        completed = _completed_evidence(selected.payload) | set(supplied_completed)
        unknown_completed = completed - set(queue.by_id)
        if unknown_completed:
            raise QueueDiscoveryError(
                "completion evidence references unknown assignment"
            )

        with self._locked():
            state = self._load_or_new()
            previous_value = state.get("queue_commit_sha")
            if previous_value is not None and not isinstance(previous_value, str):
                raise QueueDiscoveryError("checkpoint queue commit is invalid")
            previous_commit = previous_value
            if (
                previous_commit is not None
                and previous_commit != selected.queue_commit_sha
                and not source.is_ancestor(
                    previous_commit,
                    selected.queue_commit_sha,
                )
            ):
                raise QueueDiscoveryError(
                    "queue supersession does not descend from checkpoint"
                )
            assignment_states = cast(dict[str, str], state["assignment_states"])
            assignment_machines = cast(dict[str, str], state["assignment_machines"])
            completed |= {
                assignment_id
                for assignment_id, status in assignment_states.items()
                if status == "completed" and assignment_id in queue.by_id
            }
            for assignment_id in completed:
                assignment_states[assignment_id] = "completed"
            removed_active = {
                assignment_id
                for assignment_id, status in assignment_states.items()
                if status in {"running", "reconciliation_required"}
                and assignment_id not in queue.by_id
            }
            if removed_active:
                raise QueueDiscoveryError(
                    "active assignment disappeared during queue supersession"
                )
            reservation_machines = {
                reservation.assignment_id: reservation.machine
                for reservation in queue.manual_reservations
            }
            for assignment_id, reserved_machine in reservation_machines.items():
                previous_machine = assignment_machines.get(assignment_id)
                if (
                    previous_machine is not None
                    and previous_machine != reserved_machine
                    and assignment_states.get(assignment_id)
                    in {"running", "reconciliation_required"}
                ):
                    raise QueueDiscoveryError(
                        "active assignment machine ownership changed"
                    )
                assignment_machines[assignment_id] = reserved_machine

            eligible = _manual_eligible(queue, machine, completed)
            for assignment_id in eligible:
                assignment_states.setdefault(assignment_id, "ready")
            offered = tuple(
                assignment_id
                for assignment_id in eligible
                if assignment_states.get(assignment_id) == "ready"
            )
            state.update(
                {
                    "queue_commit_sha": selected.queue_commit_sha,
                    "queue_digest": selected.digest,
                    "queue_refs": list(refs),
                    "last_success_at_utc": _timestamp(now),
                    "last_attempt_count": attempts,
                    "network_failures": 0,
                    "shutdown": False,
                }
            )
            self._write(state)
        return DiscoveryResult(
            queue_commit_sha=selected.queue_commit_sha,
            queue_digest=selected.digest,
            queue_refs=refs,
            eligible_assignments=offered,
            completed_assignments=tuple(sorted(completed)),
            attempts=attempts,
            status="AUTHORITATIVE_QUEUE_DISCOVERED",
        )

    def begin(self, assignment_id: str, *, queue_digest: str, machine: str) -> None:
        with self._locked():
            state = self._load_required()
            if state.get("queue_digest") != queue_digest:
                raise QueueDiscoveryError("queue digest changed before execution")
            self._require_machine(state, assignment_id, machine)
            assignment_states = cast(dict[str, str], state["assignment_states"])
            status = assignment_states.get(assignment_id)
            if status != "ready":
                raise QueueDiscoveryError("assignment is not ready for execution")
            assignment_states[assignment_id] = "running"
            self._write(state)

    def recover_after_restart(self, *, machine: str) -> tuple[str, ...]:
        with self._locked():
            state = self._load_required()
            assignment_states = cast(dict[str, str], state["assignment_states"])
            assignment_machines = cast(dict[str, str], state["assignment_machines"])
            recovered = tuple(
                sorted(
                    assignment_id
                    for assignment_id, status in assignment_states.items()
                    if status == "running"
                    and assignment_machines.get(assignment_id) == machine
                )
            )
            for assignment_id in recovered:
                assignment_states[assignment_id] = "reconciliation_required"
            self._write(state)
            return recovered

    def reconcile(
        self,
        assignment_id: str,
        *,
        completed: bool,
        evidence_sha256: str,
        machine: str,
    ) -> None:
        if not SHA64.fullmatch(evidence_sha256):
            raise QueueDiscoveryError("reconciliation evidence digest is invalid")
        with self._locked():
            state = self._load_required()
            self._require_machine(state, assignment_id, machine)
            assignment_states = cast(dict[str, str], state["assignment_states"])
            if assignment_states.get(assignment_id) != "reconciliation_required":
                raise QueueDiscoveryError("assignment does not require reconciliation")
            assignment_states[assignment_id] = "completed" if completed else "ready"
            reconciliations = cast(dict[str, str], state["reconciliations"])
            reconciliations[assignment_id] = evidence_sha256
            self._write(state)

    def complete(
        self, assignment_id: str, *, evidence_sha256: str, machine: str
    ) -> None:
        if not SHA64.fullmatch(evidence_sha256):
            raise QueueDiscoveryError("completion evidence digest is invalid")
        with self._locked():
            state = self._load_required()
            self._require_machine(state, assignment_id, machine)
            assignment_states = cast(dict[str, str], state["assignment_states"])
            if assignment_states.get(assignment_id) != "running":
                raise QueueDiscoveryError("assignment is not running")
            assignment_states[assignment_id] = "completed"
            reconciliations = cast(dict[str, str], state["reconciliations"])
            reconciliations[assignment_id] = evidence_sha256
            self._write(state)

    def safe_shutdown(self, *, machine: str) -> tuple[str, ...]:
        with self._locked():
            state = self._load_required()
            assignment_states = cast(dict[str, str], state["assignment_states"])
            assignment_machines = cast(dict[str, str], state["assignment_machines"])
            interrupted = tuple(
                sorted(
                    assignment_id
                    for assignment_id, status in assignment_states.items()
                    if status == "running"
                    and assignment_machines.get(assignment_id) == machine
                )
            )
            for assignment_id in interrupted:
                assignment_states[assignment_id] = "reconciliation_required"
            state["shutdown"] = True
            self._write(state)
            return interrupted

    @staticmethod
    def _require_machine(
        state: dict[str, object], assignment_id: str, machine: str
    ) -> None:
        if not machine:
            raise QueueDiscoveryError("machine identity is required")
        assignment_machines = cast(dict[str, str], state["assignment_machines"])
        expected = assignment_machines.get(assignment_id)
        if expected is None:
            raise QueueDiscoveryError(
                "assignment machine ownership is unavailable; rediscovery required"
            )
        if expected != machine:
            raise QueueDiscoveryError("assignment is reserved for another machine")

    def _load_with_retry(
        self, source: QueueSource
    ) -> tuple[tuple[QueueCandidate, ...], int]:
        for attempt in range(1, self.limits.max_attempts + 1):
            try:
                candidates = source.load()
                if not candidates:
                    raise QueueDiscoveryError(
                        "no authoritative coordination queue found"
                    )
                if len(candidates) > self.limits.max_queue_candidates:
                    raise QueueDiscoveryError("queue-candidate limit exceeded")
                return candidates, attempt
            except QueueNetworkError:
                if attempt == self.limits.max_attempts:
                    with self._locked():
                        state = self._load_or_new()
                        failures = state.get("network_failures")
                        if not isinstance(failures, int) or isinstance(failures, bool):
                            raise QueueDiscoveryError(
                                "checkpoint network failure count is invalid"
                            )
                        state["network_failures"] = failures + 1
                        state["last_attempt_count"] = attempt
                        self._write(state)
                    raise QueueDiscoveryError(
                        "coordination network retry budget exhausted"
                    ) from None
                delay = min(
                    self.limits.base_retry_seconds * (2 ** (attempt - 1)),
                    self.limits.max_retry_seconds,
                )
                self.sleep(delay)
        raise AssertionError("bounded retry loop did not terminate")

    @contextmanager
    def _locked(self):  # type: ignore[no-untyped-def]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _load_or_new(self) -> dict[str, object]:
        if not self.path.exists():
            return {
                "schema": STATE_SCHEMA,
                "queue_commit_sha": None,
                "queue_digest": None,
                "queue_refs": [],
                "last_success_at_utc": None,
                "last_attempt_count": 0,
                "network_failures": 0,
                "shutdown": False,
                "assignment_states": {},
                "assignment_machines": {},
                "reconciliations": {},
                "state_digest": "",
            }
        return self._load_required()

    def _load_required(self) -> dict[str, object]:
        if self.path.is_symlink() or not self.path.is_file():
            raise QueueDiscoveryError("coordination checkpoint is unavailable")
        try:
            value: object = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise QueueDiscoveryError("coordination checkpoint is invalid") from error
        if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
            raise QueueDiscoveryError("coordination checkpoint contract is invalid")
        supplied = value.get("state_digest")
        if not isinstance(supplied, str) or not SHA64.fullmatch(supplied):
            raise QueueDiscoveryError("coordination checkpoint digest is invalid")
        unsigned = {key: item for key, item in value.items() if key != "state_digest"}
        if canonical_digest(unsigned) != supplied:
            raise QueueDiscoveryError("coordination checkpoint integrity failed")
        if "assignment_machines" not in value:
            value["assignment_machines"] = {}
        if (
            not isinstance(value.get("assignment_states"), dict)
            or not isinstance(value.get("assignment_machines"), dict)
            or not isinstance(value.get("reconciliations"), dict)
        ):
            raise QueueDiscoveryError("coordination checkpoint state is invalid")
        assignment_machines = cast(dict[object, object], value["assignment_machines"])
        if any(
            not isinstance(assignment_id, str)
            or not assignment_id
            or not isinstance(machine, str)
            or not machine
            for assignment_id, machine in assignment_machines.items()
        ):
            raise QueueDiscoveryError(
                "coordination checkpoint machine ownership is invalid"
            )
        return cast(dict[str, object], value)

    def _write(self, state: dict[str, object]) -> None:
        unsigned = {key: value for key, value in state.items() if key != "state_digest"}
        payload = {**unsigned, "state_digest": canonical_digest(unsigned)}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = -1
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary.exists():
                temporary.unlink()


def _select_authoritative(
    candidates: Sequence[QueueCandidate],
    is_ancestor: Callable[[str, str], bool],
) -> tuple[QueueCandidate, tuple[str, ...]]:
    grouped: dict[str, list[QueueCandidate]] = {}
    for candidate in candidates:
        if not candidate.ref.startswith(REMOTE_PREFIX):
            raise QueueDiscoveryError("queue candidate is not a handoff ref")
        if not all(
            SHA40.fullmatch(value)
            for value in (candidate.head_sha, candidate.queue_commit_sha)
        ):
            raise QueueDiscoveryError("queue candidate SHA is invalid")
        try:
            validate_queue(candidate.payload)
        except CoordinationError as error:
            raise QueueDiscoveryError("queue candidate contract is invalid") from error
        grouped.setdefault(candidate.queue_commit_sha, []).append(candidate)
    for values in grouped.values():
        if len({item.digest for item in values}) != 1:
            raise QueueDiscoveryError("queue commit has conflicting payloads")

    maximal = [
        commit
        for commit in grouped
        if not any(commit != other and is_ancestor(commit, other) for other in grouped)
    ]
    if len(maximal) != 1:
        raise QueueDiscoveryError("authoritative queue supersession is ambiguous")
    values = grouped[maximal[0]]
    selected = min(values, key=lambda item: item.ref)
    refs = tuple(sorted(item.ref for item in values))
    return selected, refs


def _completed_evidence(payload: dict[str, object]) -> set[str]:
    raw = payload.get("completed_evidence", [])
    if not isinstance(raw, list):
        raise QueueDiscoveryError("completed evidence must be a list")
    completed: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise QueueDiscoveryError("completed evidence entry is invalid")
        assignment_id = item.get("assignment_id")
        commit_sha = item.get("commit_sha")
        if not isinstance(assignment_id, str) or not assignment_id:
            raise QueueDiscoveryError("completed assignment ID is invalid")
        if not isinstance(commit_sha, str) or not SHA40.fullmatch(commit_sha):
            raise QueueDiscoveryError("completed assignment SHA is invalid")
        if assignment_id in completed:
            raise QueueDiscoveryError("completed assignment evidence is duplicated")
        completed.add(assignment_id)
    return completed


def _manual_eligible(
    queue: CoordinationQueue,
    machine: str,
    completed: set[str],
) -> tuple[str, ...]:
    eligible: list[str] = []
    for reservation in queue.manual_reservations:
        assignment = queue.by_id[reservation.assignment_id]
        if (
            reservation.machine == machine
            and reservation.automated_claims_blocked
            and assignment.state in ELIGIBLE_STATES
            and assignment.id not in completed
            and set(assignment.depends_on) <= completed
        ):
            eligible.append(assignment.id)
    return tuple(sorted(eligible))


def _timestamp(value: datetime | None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise QueueDiscoveryError("discovery timestamp must be timezone-aware")
    return current.astimezone(timezone.utc).isoformat()
