"""Strict validation and read-only projection for the continuous queue.

This module deliberately stops at coordination-contract validation. Durable
claims, leases, fencing, execution, and privileged Git actions remain owned by
the existing Engineering Control / Worker Control services.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from development_factory.repository import inspect_repository

QUEUE_RELATIVE_PATH = Path("development-factory/continuous-engineering-queue.v1.json")
QUEUE_SCHEMA = "twelfthats.continuous-engineering-queue.v1"
INVENTORY_SCHEMA = "twelfthats.machine-inventory.v1"
DAILY_REPORT_SCHEMA = "twelfthats.daily-engineering-report.v1"
ACTIVATION_SCHEMA = "twelfthats.machine-activation.v1"
LANES = frozenset({"LAPTOP_MASTER", "OM1", "OM2", "REVIEWER"})
STATES = frozenset(
    {
        "BLOCKED_DEPENDENCY",
        "BLOCKED_EVIDENCE",
        "BLOCKED_MACHINE_INVENTORY",
        "READY_AFTER_INVENTORY",
    }
)


class CoordinationError(ValueError):
    """The continuous coordination contract is invalid."""


@dataclass(frozen=True)
class Assignment:
    id: str
    lane: str
    priority: str
    state: str
    depends_on: tuple[str, ...]
    objective: str
    allowed_paths: tuple[str, ...] = ()
    validation: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoordinationQueue:
    schema_version: str
    status: str
    assignments: tuple[Assignment, ...]

    @property
    def by_id(self) -> dict[str, Assignment]:
        return {item.id: item for item in self.assignments}


def load_queue(repo_root: Path) -> CoordinationQueue:
    return load_queue_file(repo_root / QUEUE_RELATIVE_PATH)


def load_queue_file(path: Path) -> CoordinationQueue:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoordinationError(f"cannot load coordination queue: {error}") from error
    return validate_queue(payload)


def load_inventory_file(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoordinationError(f"cannot load machine inventory: {error}") from error
    return validate_inventory(payload)


def load_activation_file(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoordinationError(f"cannot load machine activation: {error}") from error
    if not isinstance(payload, dict):
        raise CoordinationError("machine activation must be an object")
    return payload


def validate_inventory(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise CoordinationError("machine inventory must be an object")
    if payload.get("schema") != INVENTORY_SCHEMA:
        raise CoordinationError("unsupported machine inventory schema")
    role = payload.get("role_claimed")
    if role not in {"LAPTOP", "OM1", "OM2"}:
        raise CoordinationError("machine inventory role is invalid")
    host = payload.get("host")
    repository = payload.get("repository")
    safety = payload.get("safety")
    if not isinstance(host, dict) or not isinstance(repository, dict):
        raise CoordinationError("machine inventory host/repository evidence is missing")
    if not isinstance(safety, dict):
        raise CoordinationError("machine inventory safety evidence is missing")
    for key in ("hostname", "os", "machine", "python"):
        if not isinstance(host.get(key), str) or not host[key]:
            raise CoordinationError(f"machine inventory host.{key} is missing")
    for key in ("root", "branch", "head", "origin"):
        if not isinstance(repository.get(key), str) or not repository[key]:
            raise CoordinationError(f"machine inventory repository.{key} is missing")
    head = repository["head"]
    if (
        not isinstance(head, str)
        or len(head) != 40
        or any(character not in "0123456789abcdef" for character in head)
    ):
        raise CoordinationError("machine inventory repository.head is not a SHA-1")
    for key in (
        "private_keys_read",
        "environment_values_dumped",
        "git_mutation_performed",
        "docker_container_started",
    ):
        if safety.get(key) is not False:
            raise CoordinationError(f"machine inventory safety.{key} is not false")
    return payload


def canonical_digest(value: object) -> str:
    """Return the deterministic digest used for coordination evidence."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_activation(
    payload: object, *, inventory: dict[str, object]
) -> dict[str, object]:
    """Validate a secret-free Worker Control activation receipt.

    This is evidence validation only. It does not register a worker, establish a
    session, claim an assignment, issue a lease, or authorize execution.
    """
    if not isinstance(payload, dict):
        raise CoordinationError("machine activation must be an object")
    if payload.get("schema") != ACTIVATION_SCHEMA:
        raise CoordinationError("unsupported machine activation schema")
    if payload.get("role_claimed") != inventory.get("role_claimed"):
        raise CoordinationError("activation role does not match machine inventory")
    if payload.get("machine_inventory_digest_sha256") != canonical_digest(inventory):
        raise CoordinationError("activation is not bound to the supplied inventory")
    worker = payload.get("worker")
    heartbeat = payload.get("heartbeat")
    safety = payload.get("safety")
    if not isinstance(worker, dict) or not isinstance(heartbeat, dict):
        raise CoordinationError(
            "worker activation identity/heartbeat evidence is missing"
        )
    if not isinstance(safety, dict):
        raise CoordinationError("worker activation safety evidence is missing")
    for key in (
        "worker_id",
        "provider_identifier",
        "public_key_fingerprint_sha256",
    ):
        if not isinstance(worker.get(key), str) or not worker[key]:
            raise CoordinationError(f"worker activation worker.{key} is missing")
    fingerprint = worker["public_key_fingerprint_sha256"]
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise CoordinationError("worker activation public-key fingerprint is invalid")
    capabilities = worker.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or not capabilities
        or not all(
            isinstance(capability, str) and capability for capability in capabilities
        )
    ):
        raise CoordinationError("worker activation capabilities are missing")
    if worker.get("session_state") != "connected":
        raise CoordinationError("worker activation session is not connected")
    if heartbeat.get("health") != "healthy":
        raise CoordinationError("worker activation heartbeat is not healthy")
    if (
        not isinstance(heartbeat.get("observed_at_utc"), str)
        or not heartbeat["observed_at_utc"]
    ):
        raise CoordinationError("worker activation heartbeat timestamp is missing")
    for key in (
        "private_key_material_included",
        "credential_values_included",
        "customer_data_included",
        "git_mutation_performed",
        "live_data_mutation",
    ):
        if safety.get(key) is not False:
            raise CoordinationError(f"worker activation safety.{key} is not false")
    _reject_sensitive_keys(payload)
    return payload


def _reject_sensitive_keys(value: object) -> None:
    prohibited_fragments = (
        "access_token",
        "client_secret",
        "database_url",
        "password",
        "private_key_contents",
        "secret_value",
        "token_value",
        "raw_credential",
    )
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in prohibited_fragments):
                raise CoordinationError(
                    "worker activation contains a prohibited secret-bearing field"
                )
            _reject_sensitive_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive_keys(nested)


def validate_queue(payload: object) -> CoordinationQueue:
    if not isinstance(payload, dict):
        raise CoordinationError("coordination queue must be an object")
    if payload.get("schema_version") != QUEUE_SCHEMA:
        raise CoordinationError("unsupported coordination queue schema")
    assignments = payload.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise CoordinationError("coordination queue assignments must be non-empty")
    parsed: list[Assignment] = []
    seen: set[str] = set()
    for raw in assignments:
        if not isinstance(raw, dict):
            raise CoordinationError("each assignment must be an object")
        required = {"id", "lane", "priority", "state", "depends_on", "objective"}
        if not required <= set(raw):
            raise CoordinationError(
                f"assignment is missing fields: {sorted(required - set(raw))}"
            )
        ident = raw["id"]
        lane = raw["lane"]
        state = raw["state"]
        dependencies = raw["depends_on"]
        if not all(isinstance(value, str) and value for value in (ident, lane, state)):
            raise CoordinationError(
                "assignment identity fields must be nonempty strings"
            )
        if lane not in LANES:
            raise CoordinationError(f"{ident}: unknown lane {lane}")
        if state not in STATES:
            raise CoordinationError(f"{ident}: unknown state {state}")
        if not isinstance(dependencies, list) or not all(
            isinstance(value, str) and value for value in dependencies
        ):
            raise CoordinationError(f"{ident}: depends_on must be string identifiers")
        if ident in seen:
            raise CoordinationError(f"duplicate assignment {ident}")
        seen.add(ident)
        parsed.append(
            Assignment(
                id=ident,
                lane=lane,
                priority=str(raw["priority"]),
                state=state,
                depends_on=tuple(dependencies),
                objective=str(raw["objective"]),
                allowed_paths=_string_list(
                    raw.get("allowed_paths", []), ident, "allowed_paths"
                ),
                validation=_string_list(raw.get("validation", []), ident, "validation"),
                stop_conditions=_string_list(
                    raw.get("stop_conditions", []), ident, "stop_conditions"
                ),
            )
        )

    queue = CoordinationQueue(
        schema_version=str(payload["schema_version"]),
        status=str(payload.get("status", "")),
        assignments=tuple(parsed),
    )
    by_id = queue.by_id
    for item in queue.assignments:
        unknown = set(item.depends_on) - set(by_id)
        if unknown:
            raise CoordinationError(
                f"{item.id}: unknown dependencies {sorted(unknown)}"
            )
    _assert_acyclic(queue)
    return queue


def _string_list(value: object, assignment_id: str, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise CoordinationError(f"{assignment_id}: {field} must be a list of strings")
    return tuple(str(item) for item in value)


def dependency_layers(queue: CoordinationQueue) -> tuple[tuple[str, ...], ...]:
    """Return deterministic topological layers without claiming work."""
    remaining = {item.id: set(item.depends_on) for item in queue.assignments}
    layers: list[tuple[str, ...]] = []
    while remaining:
        ready = tuple(sorted(item for item, deps in remaining.items() if not deps))
        if not ready:
            raise CoordinationError("coordination queue contains a dependency cycle")
        layers.append(ready)
        for item in ready:
            remaining.pop(item)
        for deps in remaining.values():
            deps.difference_update(ready)
    return tuple(layers)


def eligible_after_activation(
    queue: CoordinationQueue,
    active_lanes: Iterable[str],
    completed_assignments: Iterable[str] = (),
) -> tuple[str, ...]:
    """Project eligible assignments from explicit completion evidence.

    This is intentionally a projection only. Completion must come from the
    existing Worker/Engineering Control evidence; a ready predecessor is not
    treated as completed merely because it appears in an earlier dependency
    layer.
    """
    active = set(active_lanes)
    unknown = active - LANES
    if unknown:
        raise CoordinationError(f"unknown active lanes: {sorted(unknown)}")
    completed = set(completed_assignments)
    unknown_completed = completed - set(queue.by_id)
    if unknown_completed:
        raise CoordinationError(
            f"unknown completed assignments: {sorted(unknown_completed)}"
        )
    result: list[str] = []
    for layer in dependency_layers(queue):
        for ident in layer:
            item = queue.by_id[ident]
            if (
                item.lane in active
                and item.id not in completed
                and item.state
                in {
                    "READY_AFTER_INVENTORY",
                    "BLOCKED_MACHINE_INVENTORY",
                    "BLOCKED_DEPENDENCY",
                }
                and set(item.depends_on) <= completed
            ):
                result.append(item.id)
    return tuple(result)


def _assert_acyclic(queue: CoordinationQueue) -> None:
    by_id = queue.by_id
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ident: str) -> None:
        if ident in visiting:
            raise CoordinationError(f"dependency cycle includes {ident}")
        if ident in visited:
            return
        visiting.add(ident)
        for dependency in by_id[ident].depends_on:
            visit(dependency)
        visiting.remove(ident)
        visited.add(ident)

    for ident in by_id:
        visit(ident)


def build_daily_report(
    repo_root: Path,
    *,
    inventory_paths: Iterable[Path] = (),
    activation_paths: Iterable[Path] = (),
    active_lanes: Iterable[str] = (),
    completed_assignments: Iterable[str] = (),
    latest_report_path: Path | None = None,
) -> dict[str, object]:
    """Build a secret-free daily projection from existing evidence only."""
    queue = load_queue(repo_root)
    repository = inspect_repository(repo_root)
    active = tuple(active_lanes)
    inventories = [
        _inventory_summary(load_inventory_file(path), path) for path in inventory_paths
    ]
    inventory_payloads = [load_inventory_file(path) for path in inventory_paths]
    activations: list[dict[str, object]] = []
    activated_lanes: list[str] = []
    for path in activation_paths:
        activation = load_activation_file(path)
        role = activation.get("role_claimed")
        inventory = next(
            (item for item in inventory_payloads if item.get("role_claimed") == role),
            None,
        )
        if inventory is None:
            raise CoordinationError(
                f"activation {path} has no matching machine inventory"
            )
        validate_activation(activation, inventory=inventory)
        lane = _inventory_role_for_lane(str(role))
        activated_lanes.append(lane)
        activations.append(
            {
                "role": role,
                "receipt": str(path),
                "worker_id_present": True,
                "session_state": "connected",
                "heartbeat_health": "healthy",
            }
        )
    latest = _load_latest_validation(
        latest_report_path or repo_root / ".development-factory/latest.json",
        current_head=repository.head,
    )
    state_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {}
    for assignment in queue.assignments:
        state_counts[assignment.state] = state_counts.get(assignment.state, 0) + 1
        lane_counts[assignment.lane] = lane_counts.get(assignment.lane, 0) + 1
    return {
        "schema": DAILY_REPORT_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authority": {
            "application_integration_lane": "LAPTOP_MASTER",
            "factory_lane": "OM1",
            "operations_data_lane": "OM2",
            "independent_reviewer": "REVIEWER",
            "claims_and_leases": "existing Engineering Control / Worker Control",
            "live_mutation": False,
        },
        "queue": {
            "status": queue.status,
            "assignment_count": len(queue.assignments),
            "state_counts": state_counts,
            "lane_counts": lane_counts,
            "active_lanes_supplied": list(active),
            "activated_lanes_verified": sorted(set(activated_lanes)),
            "eligible_after_supplied_activation": list(
                eligible_after_activation(queue, active, completed_assignments)
            ),
            "completed_assignments_supplied": sorted(set(completed_assignments)),
        },
        "repository": {
            "branch": repository.branch,
            "head": repository.head,
            "working_tree_clean": repository.working_tree_clean,
            "index_clean": repository.index_clean,
        },
        "machines": inventories,
        "activations": activations,
        "unverified_lanes": sorted(
            lane
            for lane in ("LAPTOP_MASTER", "OM1", "OM2", "REVIEWER")
            if not any(
                item["role"] == _inventory_role_for_lane(lane) for item in inventories
            )
        ),
        "validation": latest,
        "utilization": {
            "status": "UNAVAILABLE",
            "reason": "Machine inventory does not collect process utilization.",
        },
        "safety": {
            "source_values_read": False,
            "private_keys_read": False,
            "git_mutation_performed": False,
            "live_data_mutation": False,
        },
    }


def write_daily_report(report: dict[str, object], json_path: Path) -> tuple[Path, Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path = json_path.with_suffix(".md")
    markdown_path.write_text(render_daily_report(report), encoding="utf-8")
    return json_path, markdown_path


def render_daily_report(report: dict[str, object]) -> str:
    queue = report["queue"]
    assert isinstance(queue, dict)
    eligible = queue["eligible_after_supplied_activation"]
    assert isinstance(eligible, list)
    unverified_lanes = report["unverified_lanes"]
    assert isinstance(unverified_lanes, list)
    lines = [
        "# TwelveHats Daily Engineering Report",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Queue status: `{queue['status']}`",
        f"- Assignments: `{queue['assignment_count']}`",
        f"- Eligible after supplied activation: {', '.join(eligible) or 'NONE'}",
        "",
        "## Machines",
        "",
    ]
    machines = report["machines"]
    assert isinstance(machines, list)
    if machines:
        lines.extend(
            f"- `{item['role']}` — {item['hostname']} — {item['branch']} @ `{item['head']}`; clean={item['clean']}"
            for item in machines
        )
    else:
        lines.append("- No machine inventory receipts supplied.")
    lines.extend(
        [
            "",
            "## Unverified lanes",
            "",
            f"- {', '.join(unverified_lanes) or 'None.'}",
            "",
            "## Validation",
            "",
        ]
    )
    validation = report["validation"]
    assert isinstance(validation, dict)
    repository = report["repository"]
    assert isinstance(repository, dict)
    lines.append(f"- Status: `{validation.get('status', 'UNAVAILABLE')}`")
    lines.append(f"- Readiness: `{validation.get('readiness', 'UNAVAILABLE')}`")
    lines.append(f"- Validation HEAD: `{validation.get('head', 'UNAVAILABLE')}`")
    lines.append(f"- Current HEAD: `{repository['head']}`")
    lines.extend(
        [
            "",
            "## Resource utilization",
            "",
            "- UNAVAILABLE — inventory receipts do not collect process utilization.",
            "",
            "This report is an evidence projection only; it does not claim work, create leases, or authorize mutations.",
            "",
        ]
    )
    return "\n".join(lines)


def _inventory_role_for_lane(lane: str) -> str:
    return "LAPTOP" if lane == "LAPTOP_MASTER" else lane


def _inventory_summary(payload: dict[str, object], path: Path) -> dict[str, object]:
    host = payload["host"]
    repository = payload["repository"]
    resources = payload.get("resources", {})
    assert isinstance(host, dict)
    assert isinstance(repository, dict)
    assert isinstance(resources, dict)
    return {
        "role": payload["role_claimed"],
        "receipt": str(path),
        "hostname": host["hostname"],
        "os": host["os"],
        "branch": repository["branch"],
        "head": repository["head"],
        "clean": repository.get("status_clean") is True,
        "free_bytes_at_repo": resources.get("free_bytes_at_repo"),
        "host_memory_bytes": resources.get("host_memory_bytes"),
        "safety": payload["safety"],
    }


def _load_latest_validation(path: Path, *, current_head: str) -> dict[str, object]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "UNAVAILABLE",
            "reason": "No readable latest validation report.",
        }
    if not isinstance(payload, dict):
        return {
            "status": "UNAVAILABLE",
            "reason": "Latest validation report is not an object.",
        }
    repository = payload.get("repository")
    observed_head = (
        repository.get("head", "UNAVAILABLE")
        if isinstance(repository, dict)
        else "UNAVAILABLE"
    )
    status = "AVAILABLE" if observed_head == current_head else "STALE"
    return {
        "status": status,
        "readiness": payload.get("readiness", "UNAVAILABLE"),
        "head": observed_head,
        "stale_against_head": current_head if status == "STALE" else None,
        "blocking_failures": payload.get("blocking_failures", []),
        "generated_at": payload.get("generated_at", "UNAVAILABLE"),
    }


__all__ = [
    "DAILY_REPORT_SCHEMA",
    "Assignment",
    "CoordinationError",
    "CoordinationQueue",
    "build_daily_report",
    "dependency_layers",
    "eligible_after_activation",
    "load_inventory_file",
    "load_queue",
    "load_queue_file",
    "validate_inventory",
    "validate_queue",
    "write_daily_report",
]
