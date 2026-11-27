"""Persistent, identity-bound execution for authorized coordination assignments.

The runner intentionally supports a small set of built-in, read-only engineering
qualification profiles.  It does not accept shell commands, issue Worker Control
claims or leases, commit, push, merge, deploy, or access protected data.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import resource
import shutil
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from development_factory.coordination import Assignment, ManualReservation
from development_factory.queue_discovery import (
    DiscoveryResult,
    QueueDiscoverySupervisor,
    QueueSource,
    assignment_contract_digest,
)

PLAN_SCHEMA = "twelfthats.unattended-execution-plan.v1"
RUNTIME_SCHEMA = "twelfthats.unattended-supervisor-state.v1"
EVIDENCE_SCHEMA = "twelfthats.unattended-assignment-evidence.v1"
SHA64_LENGTH = 64
SUPPORTED_PROFILES = frozenset({"supervisor_continuation", "supervisor_unattended"})


class UnattendedSupervisorError(ValueError):
    """The persistent supervisor cannot continue safely."""


@dataclass(frozen=True)
class PlanEntry:
    assignment_id: str
    contract_sha256: str
    profile: str


@dataclass(frozen=True)
class ExecutionPlan:
    machine: str
    execution_identity: str
    authority_ref: str
    authority_sha: str
    assignments: tuple[PlanEntry, ...]
    allow_authority_profile_extensions: bool = False
    supersedes_plan_sha256: str | None = None

    @property
    def by_id(self) -> dict[str, PlanEntry]:
        return {item.assignment_id: item for item in self.assignments}


@dataclass(frozen=True)
class SupervisorLimits:
    poll_seconds: float = 60
    max_cycles: int = 0
    max_assignments: int = 8
    max_runtime_seconds: float = 21_600
    minimum_free_bytes: int = 5 * 1024 * 1024 * 1024
    maximum_rss_bytes: int = 512 * 1024 * 1024

    def validate(self) -> None:
        if not 1 <= self.poll_seconds <= 3_600:
            raise UnattendedSupervisorError("poll interval is outside safe bounds")
        if not 0 <= self.max_cycles <= 10_000:
            raise UnattendedSupervisorError("cycle limit is outside safe bounds")
        if not 1 <= self.max_assignments <= 32:
            raise UnattendedSupervisorError("assignment limit is outside safe bounds")
        if not 60 <= self.max_runtime_seconds <= 86_400:
            raise UnattendedSupervisorError("runtime limit is outside safe bounds")
        if not 1024**3 <= self.minimum_free_bytes <= 1024**4:
            raise UnattendedSupervisorError("free-space limit is outside safe bounds")
        if not 64 * 1024**2 <= self.maximum_rss_bytes <= 4 * 1024**3:
            raise UnattendedSupervisorError("memory limit is outside safe bounds")


@dataclass(frozen=True)
class ResourceSnapshot:
    logical_cpu_count: int
    load_average_1m: float
    free_bytes: int
    process_max_rss_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "logical_cpu_count": self.logical_cpu_count,
            "load_average_1m": self.load_average_1m,
            "free_bytes": self.free_bytes,
            "process_max_rss_bytes": self.process_max_rss_bytes,
        }


@dataclass(frozen=True)
class ExecutionContext:
    discovery: DiscoveryResult
    start_count: int
    completed_before: tuple[str, ...]
    resources: ResourceSnapshot
    checkpoint_path: Path


@dataclass(frozen=True)
class SupervisorRunResult:
    status: str
    cycles: int
    executed_assignments: tuple[str, ...]
    recovered_assignments: tuple[str, ...]


class AssignmentExecutor(Protocol):
    def execute(
        self,
        assignment: Assignment,
        reservation: ManualReservation,
        entry: PlanEntry,
        context: ExecutionContext,
    ) -> dict[str, object]: ...


class OperationalQualificationExecutor:
    """Produce evidence from live discovery and durable supervisor state."""

    def execute(
        self,
        assignment: Assignment,
        reservation: ManualReservation,
        entry: PlanEntry,
        context: ExecutionContext,
    ) -> dict[str, object]:
        checkpoint = context.checkpoint_path
        if checkpoint.is_symlink() or not checkpoint.is_file():
            raise UnattendedSupervisorError("durable checkpoint is unavailable")
        if stat.S_IMODE(checkpoint.stat().st_mode) != 0o600:
            raise UnattendedSupervisorError("durable checkpoint mode is not 0600")
        if entry.profile == "supervisor_unattended" and context.start_count < 2:
            raise UnattendedSupervisorError(
                "unattended qualification requires an observed supervisor restart"
            )
        if not set(assignment.depends_on) <= set(context.completed_before):
            raise UnattendedSupervisorError("assignment dependencies are incomplete")
        return {
            "schema": EVIDENCE_SCHEMA,
            "assignment_id": assignment.id,
            "profile": entry.profile,
            "observed_at_utc": _timestamp(),
            "authority": {
                "queue_commit_sha": context.discovery.queue_commit_sha,
                "queue_digest_sha256": context.discovery.queue_digest,
                "queue_refs": list(context.discovery.queue_refs),
                "execution_identity": context.discovery.execution_identity,
                "reservation_machine": reservation.machine,
                "contract_sha256": entry.contract_sha256,
            },
            "operation": {
                "process_id": os.getpid(),
                "supervisor_start_count": context.start_count,
                "checkpoint_mode": "0600",
                "dependencies_completed": list(assignment.depends_on),
                "restart_observed": context.start_count >= 2,
                "duplicate_execution_prevented": True,
                "current_authority_discovered": True,
            },
            "resources": context.resources.to_dict(),
            "safety": {
                "worker_control_claim_created": False,
                "worker_control_lease_created": False,
                "automatic_approval": False,
                "git_commit_performed": False,
                "git_push_performed": False,
                "merge_performed": False,
                "deployment_performed": False,
                "protected_data_accessed": False,
                "environment_dumped": False,
                "secret_persisted": False,
            },
            "result": "PASS",
        }


class PersistentSupervisor:
    def __init__(
        self,
        repo_root: Path,
        *,
        discovery: QueueDiscoverySupervisor,
        source: QueueSource,
        plan_path: Path,
        runtime_state_path: Path,
        machine: str,
        execution_identity: str,
        executor: AssignmentExecutor | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        resource_probe: Callable[[Path], ResourceSnapshot] | None = None,
    ) -> None:
        self.root = repo_root.resolve()
        self.discovery = discovery
        self.source = source
        self.plan_path = plan_path.resolve()
        self.runtime_path = runtime_state_path.resolve()
        self.runtime_lock_path = self.runtime_path.with_suffix(
            self.runtime_path.suffix + ".lock"
        )
        self.stop_path = self.runtime_path.with_suffix(
            self.runtime_path.suffix + ".stop"
        )
        self.evidence_root = self.runtime_path.parent / "evidence"
        self.machine = machine
        self.execution_identity = execution_identity
        self.executor = executor or OperationalQualificationExecutor()
        self.sleep = sleep
        self.monotonic = monotonic
        self.resource_probe = resource_probe or _resource_snapshot

    def run(self, *, limits: SupervisorLimits) -> SupervisorRunResult:
        limits.validate()
        plan = load_execution_plan(self.plan_path)
        if (
            plan.machine != self.machine
            or plan.execution_identity != self.execution_identity
        ):
            raise UnattendedSupervisorError(
                "execution plan does not match supervisor identity"
            )
        self.runtime_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.runtime_lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise UnattendedSupervisorError(
                    "another persistent supervisor instance is active"
                ) from error
            return self._run_locked(plan, limits)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _run_locked(
        self, plan: ExecutionPlan, limits: SupervisorLimits
    ) -> SupervisorRunResult:
        state = self._load_or_new(plan)
        stale_pid = state.get("active_pid")
        if stale_pid is not None:
            if not isinstance(stale_pid, int) or isinstance(stale_pid, bool):
                raise UnattendedSupervisorError(
                    "runtime checkpoint active PID is invalid"
                )
            # The process owns the exclusive runtime lock at this point.  A PID
            # recorded by an earlier owner therefore cannot represent an active
            # supervisor, even if the operating system has since reused it.
            state["active_pid"] = None
            state["last_stale_pid"] = stale_pid
            state["last_stale_pid_recovered_at_utc"] = _timestamp()
            self._event(state, "STALE_ACTIVE_PID_RECOVERED")
        state["start_count"] = _integer(state, "start_count") + 1
        state["active_pid"] = os.getpid()
        state["last_started_at_utc"] = _timestamp()
        state["last_heartbeat_at_utc"] = state["last_started_at_utc"]
        self._event(state, "SUPERVISOR_STARTED")
        self._write_state(state)
        start_count = cast(int, state["start_count"])
        recovered = self._recover(state)
        if recovered:
            self._event(state, "RECOVERY_REQUIRES_EVIDENCE", recovered)
            state["active_pid"] = None
            self._write_state(state)
            return SupervisorRunResult("RECOVERY_REQUIRED", 0, (), recovered)

        started_at = self.monotonic()
        cycles = 0
        executed: list[str] = []
        status = "RUNTIME_LIMIT_REACHED"
        try:
            while self.monotonic() - started_at < limits.max_runtime_seconds:
                if self.stop_path.exists():
                    self._event(state, "STOP_REQUESTED")
                    status = "SAFE_SHUTDOWN"
                    break
                cycles += 1
                resources = self.resource_probe(self.root)
                self._require_resources(resources, limits)
                state["last_resources"] = resources.to_dict()
                discovery = self.discovery.discover(
                    self.source,
                    machine=self.machine,
                    execution_identity=self.execution_identity,
                )
                state["last_heartbeat_at_utc"] = _timestamp()
                state["last_observed_authority_sha"] = discovery.queue_commit_sha
                state["last_observed_queue_sha256"] = discovery.queue_digest
                if plan.authority_ref not in discovery.queue_refs:
                    raise UnattendedSupervisorError(
                        "execution plan authority ref is not authoritative"
                    )
                if not self.source.is_ancestor(
                    plan.authority_sha, discovery.queue_commit_sha
                ):
                    raise UnattendedSupervisorError(
                        "discovered authority does not descend from plan baseline"
                    )
                offered = discovery.eligible_assignments
                if offered:
                    assignment_id = offered[0]
                    self._execute_assignment(
                        state, plan, discovery, assignment_id, resources, start_count
                    )
                    executed.append(assignment_id)
                    if len(executed) >= limits.max_assignments:
                        status = "ASSIGNMENT_LIMIT_REACHED"
                        break
                    continue
                self._event(state, "IDLE_QUEUE")
                self._write_state(state)
                if limits.max_cycles and cycles >= limits.max_cycles:
                    status = "CYCLE_LIMIT_REACHED"
                    break
                self.sleep(limits.poll_seconds)
            else:
                status = "RUNTIME_LIMIT_REACHED"
        except Exception as error:
            interrupted = (
                self.discovery.safe_shutdown(
                    machine=self.machine,
                    execution_identity=self.execution_identity,
                )
                if self.discovery.path.exists()
                else ()
            )
            self._event(state, "FAIL_CLOSED", interrupted)
            state["last_error"] = _safe_error(error)
            state["active_pid"] = None
            self._write_state(state)
            raise
        state["active_pid"] = None
        state["last_exit_status"] = status
        state["last_exited_at_utc"] = _timestamp()
        self._event(state, status)
        self._write_state(state)
        return SupervisorRunResult(status, cycles, tuple(executed), ())

    def _execute_assignment(
        self,
        state: dict[str, object],
        plan: ExecutionPlan,
        discovery: DiscoveryResult,
        assignment_id: str,
        resources: ResourceSnapshot,
        start_count: int,
    ) -> None:
        assignment = discovery.queue.by_id[assignment_id]
        reservation = discovery.queue.manual_reservation_by_id[assignment_id]
        actual_digest = assignment_contract_digest(assignment, reservation)
        entry = plan.by_id.get(assignment_id)
        if entry is None:
            profile = assignment.execution_profile
            if (
                not plan.allow_authority_profile_extensions
                or profile not in SUPPORTED_PROFILES
            ):
                raise UnattendedSupervisorError(
                    f"eligible assignment is not in the execution plan: {assignment_id}"
                )
            entry = PlanEntry(assignment_id, actual_digest, profile)
        if actual_digest != entry.contract_sha256:
            raise UnattendedSupervisorError(
                f"assignment contract changed: {assignment_id}"
            )
        assignments = cast(dict[str, object], state["assignments"])
        previous = assignments.get(assignment_id)
        if isinstance(previous, dict) and previous.get("status") == "completed":
            raise UnattendedSupervisorError(
                f"completed assignment was offered again: {assignment_id}"
            )
        self.discovery.begin(
            assignment_id,
            queue_digest=discovery.queue_digest,
            machine=self.machine,
            execution_identity=self.execution_identity,
        )
        assignments[assignment_id] = {
            "status": "running",
            "attempts": _attempt_count(previous) + 1,
            "started_at_utc": _timestamp(),
            "contract_sha256": actual_digest,
        }
        state["current_assignment"] = assignment_id
        self._event(state, "ASSIGNMENT_STARTED", (assignment_id,))
        self._write_state(state)
        context = ExecutionContext(
            discovery=discovery,
            start_count=start_count,
            completed_before=discovery.completed_assignments,
            resources=resources,
            checkpoint_path=self.discovery.path,
        )
        evidence = self.executor.execute(assignment, reservation, entry, context)
        evidence_path, evidence_sha = self._write_evidence(assignment_id, evidence)
        assignments[assignment_id] = {
            **cast(dict[str, object], assignments[assignment_id]),
            "status": "evidence_written",
            "evidence_path": str(evidence_path),
            "evidence_sha256": evidence_sha,
        }
        self._write_state(state)
        self.discovery.complete(
            assignment_id,
            evidence_sha256=evidence_sha,
            machine=self.machine,
            execution_identity=self.execution_identity,
        )
        assignments[assignment_id] = {
            **cast(dict[str, object], assignments[assignment_id]),
            "status": "completed",
            "completed_at_utc": _timestamp(),
        }
        state["current_assignment"] = None
        self._event(state, "ASSIGNMENT_COMPLETED", (assignment_id,))
        self._write_state(state)

    def _recover(self, state: dict[str, object]) -> tuple[str, ...]:
        if not self.discovery.path.exists():
            return ()
        recovered = self.discovery.recover_after_restart(
            machine=self.machine,
            execution_identity=self.execution_identity,
        )
        if not recovered:
            return ()
        assignments = cast(dict[str, object], state["assignments"])
        unresolved: list[str] = []
        for assignment_id in recovered:
            record = assignments.get(assignment_id)
            if (
                not isinstance(record, dict)
                or record.get("status") != "evidence_written"
            ):
                unresolved.append(assignment_id)
                continue
            path_value = record.get("evidence_path")
            digest = record.get("evidence_sha256")
            if not isinstance(path_value, str) or not _is_sha256(digest):
                unresolved.append(assignment_id)
                continue
            path = Path(path_value)
            if not path.is_file() or _file_digest(path) != digest:
                unresolved.append(assignment_id)
                continue
            self.discovery.reconcile(
                assignment_id,
                completed=True,
                evidence_sha256=cast(str, digest),
                machine=self.machine,
                execution_identity=self.execution_identity,
            )
            record["status"] = "completed"
            record["recovered_at_utc"] = _timestamp()
        self._write_state(state)
        return tuple(sorted(unresolved))

    def _load_or_new(self, plan: ExecutionPlan) -> dict[str, object]:
        if not self.runtime_path.exists():
            return {
                "schema": RUNTIME_SCHEMA,
                "machine": self.machine,
                "execution_identity": self.execution_identity,
                "authority_ref": plan.authority_ref,
                "authority_sha": plan.authority_sha,
                "plan_sha256": _file_digest(self.plan_path),
                "start_count": 0,
                "active_pid": None,
                "current_assignment": None,
                "assignments": {},
                "events": [],
                "last_resources": None,
                "last_heartbeat_at_utc": None,
                "last_observed_authority_sha": None,
                "last_observed_queue_sha256": None,
                "last_stale_pid": None,
                "last_stale_pid_recovered_at_utc": None,
                "last_error": None,
                "last_exit_status": None,
                "state_digest": "",
            }
        state = _load_secure_state(self.runtime_path, RUNTIME_SCHEMA)
        current_plan_sha = _file_digest(self.plan_path)
        for field, expected in (
            ("machine", self.machine),
            ("execution_identity", self.execution_identity),
            ("authority_ref", plan.authority_ref),
            ("authority_sha", plan.authority_sha),
        ):
            if state.get(field) != expected:
                raise UnattendedSupervisorError(f"runtime checkpoint {field} mismatch")
        previous_plan_sha = state.get("plan_sha256")
        if previous_plan_sha != current_plan_sha:
            if (
                not _is_sha256(previous_plan_sha)
                or plan.supersedes_plan_sha256 != previous_plan_sha
            ):
                raise UnattendedSupervisorError(
                    "runtime checkpoint plan supersession is unauthorized"
                )
            state["plan_sha256"] = current_plan_sha
            state["previous_plan_sha256"] = previous_plan_sha
            state["plan_superseded_at_utc"] = _timestamp()
            self._event(state, "EXECUTION_PLAN_SUPERSEDED")
            self._write_state(state)
        if not isinstance(state.get("assignments"), dict) or not isinstance(
            state.get("events"), list
        ):
            raise UnattendedSupervisorError("runtime checkpoint structure is invalid")
        return state

    def _write_state(self, state: dict[str, object]) -> None:
        _write_secure_state(self.runtime_path, state)

    def _write_evidence(
        self, assignment_id: str, evidence: dict[str, object]
    ) -> tuple[Path, str]:
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        path = self.evidence_root / f"{assignment_id}.json"
        if path.exists():
            raise UnattendedSupervisorError(
                f"assignment evidence already exists: {assignment_id}"
            )
        _write_secure_json(path, evidence)
        return path, _file_digest(path)

    @staticmethod
    def _event(
        state: dict[str, object], name: str, assignments: tuple[str, ...] = ()
    ) -> None:
        events = cast(list[object], state["events"])
        events.append(
            {
                "at_utc": _timestamp(),
                "event": name,
                "assignments": list(assignments),
            }
        )
        del events[:-128]

    @staticmethod
    def _require_resources(
        resources: ResourceSnapshot, limits: SupervisorLimits
    ) -> None:
        if resources.free_bytes < limits.minimum_free_bytes:
            raise UnattendedSupervisorError("minimum free disk boundary reached")
        if resources.process_max_rss_bytes > limits.maximum_rss_bytes:
            raise UnattendedSupervisorError("supervisor memory boundary reached")


def load_execution_plan(path: Path) -> ExecutionPlan:
    if path.is_symlink() or not path.is_file():
        raise UnattendedSupervisorError("execution plan is unavailable")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UnattendedSupervisorError("execution plan is invalid") from error
    if not isinstance(payload, dict) or payload.get("schema") != PLAN_SCHEMA:
        raise UnattendedSupervisorError("execution plan contract is invalid")
    _reject_secret_fields(payload)
    machine = payload.get("machine")
    identity = payload.get("execution_identity")
    authority_ref = payload.get("authority_ref")
    authority_sha = payload.get("authority_sha")
    allow_extensions = payload.get("allow_authority_profile_extensions", False)
    supersedes_plan_sha = payload.get("supersedes_plan_sha256")
    raw_assignments = payload.get("assignments")
    safety = payload.get("safety")
    if not all(
        isinstance(item, str) and item
        for item in (machine, identity, authority_ref, authority_sha)
    ):
        raise UnattendedSupervisorError("execution plan identity is invalid")
    if (
        not isinstance(authority_sha, str)
        or len(authority_sha) != 40
        or any(character not in "0123456789abcdef" for character in authority_sha)
    ):
        raise UnattendedSupervisorError("execution plan authority SHA is invalid")
    if not isinstance(raw_assignments, list) or not raw_assignments:
        raise UnattendedSupervisorError("execution plan assignments are missing")
    if not isinstance(allow_extensions, bool):
        raise UnattendedSupervisorError(
            "execution plan authority extension policy is invalid"
        )
    if supersedes_plan_sha is not None and not _is_sha256(supersedes_plan_sha):
        raise UnattendedSupervisorError("execution plan superseded digest is invalid")
    if not isinstance(safety, dict):
        raise UnattendedSupervisorError("execution plan safety boundary is missing")
    for field in (
        "worker_control_claims",
        "worker_control_leases",
        "automatic_commit",
        "automatic_push",
        "automatic_merge",
        "automatic_deploy",
        "protected_execution",
    ):
        if safety.get(field) is not False:
            raise UnattendedSupervisorError(
                f"execution plan safety.{field} must be false"
            )
    entries: list[PlanEntry] = []
    seen: set[str] = set()
    for raw in raw_assignments:
        if not isinstance(raw, dict):
            raise UnattendedSupervisorError("execution plan assignment is invalid")
        assignment_id = raw.get("assignment_id")
        contract_sha = raw.get("contract_sha256")
        profile = raw.get("profile")
        if not isinstance(assignment_id, str) or not assignment_id:
            raise UnattendedSupervisorError("planned assignment ID is invalid")
        if assignment_id in seen:
            raise UnattendedSupervisorError("planned assignment is duplicated")
        if not _is_sha256(contract_sha):
            raise UnattendedSupervisorError("planned contract digest is invalid")
        if profile not in SUPPORTED_PROFILES:
            raise UnattendedSupervisorError("planned execution profile is unsupported")
        seen.add(assignment_id)
        entries.append(
            PlanEntry(assignment_id, cast(str, contract_sha), cast(str, profile))
        )
    return ExecutionPlan(
        cast(str, machine),
        cast(str, identity),
        cast(str, authority_ref),
        authority_sha,
        tuple(entries),
        allow_extensions,
        cast(str, supersedes_plan_sha) if supersedes_plan_sha is not None else None,
    )


def _resource_snapshot(root: Path) -> ResourceSnapshot:
    cpu_count = os.cpu_count() or 1
    load_average = os.getloadavg()[0]
    free_bytes = shutil.disk_usage(root).free
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    if os.uname().sysname != "Darwin":
        rss *= 1024
    return ResourceSnapshot(cpu_count, load_average, free_bytes, rss)


def _load_secure_state(path: Path, schema: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise UnattendedSupervisorError("runtime checkpoint is unavailable")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise UnattendedSupervisorError("runtime checkpoint mode is not 0600")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UnattendedSupervisorError("runtime checkpoint is invalid") from error
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise UnattendedSupervisorError("runtime checkpoint contract is invalid")
    supplied = value.get("state_digest")
    unsigned = {key: item for key, item in value.items() if key != "state_digest"}
    if not _is_sha256(supplied) or _digest(unsigned) != supplied:
        raise UnattendedSupervisorError("runtime checkpoint integrity failed")
    return value


def _write_secure_state(path: Path, state: dict[str, object]) -> None:
    unsigned = {key: value for key, value in state.items() if key != "state_digest"}
    _write_secure_json(path, {**unsigned, "state_digest": _digest(unsigned)})


def _write_secure_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA64_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _integer(state: dict[str, object], field: str) -> int:
    value = state.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise UnattendedSupervisorError(f"runtime checkpoint {field} is invalid")
    return value


def _attempt_count(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    attempts = value.get("attempts", 0)
    return attempts if isinstance(attempts, int) and attempts >= 0 else 0


def _safe_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {str(error)[:240]}"


def _reject_secret_fields(value: object) -> None:
    prohibited = (
        "access_token",
        "client_secret",
        "database_url",
        "password",
        "private_key",
        "secret_value",
        "token_value",
        "raw_credential",
    )
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in prohibited):
                raise UnattendedSupervisorError(
                    "execution plan contains a prohibited secret-bearing field"
                )
            _reject_secret_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_fields(nested)


__all__ = [
    "ExecutionPlan",
    "OperationalQualificationExecutor",
    "PersistentSupervisor",
    "PlanEntry",
    "ResourceSnapshot",
    "SupervisorLimits",
    "SupervisorRunResult",
    "UnattendedSupervisorError",
    "load_execution_plan",
]
