#!/usr/bin/env python3
"""Validate the durable Master Completion Program objective register."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_STATUSES = {
    "NOT STARTED",
    "IN PROGRESS",
    "IMPLEMENTED",
    "TESTING",
    "INTEGRATION READY",
    "INTEGRATED",
    "ACCEPTED",
    "BLOCKED",
}
REQUIRED_IDS = {
    "OBJ-001",
    "OBJ-002",
    "OBJ-003",
    "OBJ-010",
    "OBJ-011",
    "OBJ-020",
    "OBJ-021",
    "OBJ-022",
    "OBJ-030",
    "OBJ-031",
    "OBJ-032",
    "OBJ-040",
    "OBJ-041",
    "OBJ-050",
    "OBJ-051",
    "OBJ-052",
    "OBJ-053",
    "OBJ-060",
    "OBJ-061",
    "OBJ-062",
    "OBJ-070",
    "OBJ-080",
    "OBJ-081",
    "OBJ-090",
    "OBJ-091",
    "OBJ-092",
    "OBJ-100",
    "OBJ-101",
    "OBJ-102",
    "OBJ-103",
    "OBJ-110",
    "OBJ-111",
}
REQUIRED_FIELDS = {
    "id",
    "domain",
    "outcome",
    "status",
    "known_defects",
    "ownership",
    "assignment",
    "dependencies",
    "implementation_steps",
    "data_migrations",
    "security_permissions",
    "acceptance_tests",
    "simulator_scenarios",
    "integration_requirements",
    "evidence_required",
    "priority",
    "estimated_remaining_hours",
    "blocker",
    "completion_evidence",
}


def validate(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if document.get("schema_version") != "twelvehats-master-objective-register/v1":
        errors.append("unsupported schema_version")
    objectives = document.get("objectives")
    if not isinstance(objectives, list):
        return [*errors, "objectives must be a list"]
    seen: set[str] = set()
    for index, objective in enumerate(objectives):
        if not isinstance(objective, dict):
            errors.append(f"objective[{index}] must be an object")
            continue
        objective_id = objective.get("id", f"objective[{index}]")
        missing = REQUIRED_FIELDS - objective.keys()
        if missing:
            errors.append(f"{objective_id}: missing {sorted(missing)}")
        if objective.get("status") not in ALLOWED_STATUSES:
            errors.append(f"{objective_id}: invalid status {objective.get('status')!r}")
        if objective_id in seen:
            errors.append(f"{objective_id}: duplicate id")
        seen.add(str(objective_id))
        ownership = objective.get("ownership")
        if (
            not isinstance(ownership, dict)
            or not ownership.get("repository")
            or not ownership.get("modules")
        ):
            errors.append(f"{objective_id}: incomplete ownership")
        assignment = objective.get("assignment")
        if (
            not isinstance(assignment, dict)
            or not assignment.get("worker")
            or not assignment.get("machine")
        ):
            errors.append(f"{objective_id}: incomplete assignment")
        blocker = objective.get("blocker")
        if (
            not isinstance(blocker, dict)
            or "state" not in blocker
            or "escalation" not in blocker
        ):
            errors.append(f"{objective_id}: incomplete blocker")
    missing_ids = REQUIRED_IDS - seen
    unexpected_ids = seen - REQUIRED_IDS
    if missing_ids:
        errors.append(f"missing objective ids: {sorted(missing_ids)}")
    if unexpected_ids:
        errors.append(f"unexpected objective ids: {sorted(unexpected_ids)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path(
            "docs/operations/completion-program/MASTER.OBJECTIVE.REGISTER.20261119.json"
        ),
    )
    arguments = parser.parse_args()
    errors = validate(arguments.path)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"PASS objectives={len(REQUIRED_IDS)} path={arguments.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
