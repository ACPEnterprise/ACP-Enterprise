"""Strict validation and read-only projection for the continuous queue.

This module deliberately stops at coordination-contract validation. Durable
claims, leases, fencing, execution, and privileged Git actions remain owned by
the existing Engineering Control / Worker Control services.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

QUEUE_RELATIVE_PATH = Path("development-factory/continuous-engineering-queue.v1.json")
QUEUE_SCHEMA = "twelfthats.continuous-engineering-queue.v1"
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
    queue: CoordinationQueue, active_lanes: Iterable[str]
) -> tuple[str, ...]:
    """Project eligible assignments; durable claiming remains elsewhere."""
    active = set(active_lanes)
    unknown = active - LANES
    if unknown:
        raise CoordinationError(f"unknown active lanes: {sorted(unknown)}")
    completed: set[str] = set()
    result: list[str] = []
    for layer in dependency_layers(queue):
        for ident in layer:
            item = queue.by_id[ident]
            if (
                item.lane in active
                and item.state == "READY_AFTER_INVENTORY"
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


__all__ = [
    "Assignment",
    "CoordinationError",
    "CoordinationQueue",
    "dependency_layers",
    "eligible_after_activation",
    "load_queue",
    "load_queue_file",
    "validate_queue",
]
