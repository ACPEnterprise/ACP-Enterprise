from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from development_factory.models import CheckDefinition


class ManifestError(ValueError):
    pass


def load_manifest(path: Path) -> tuple[CheckDefinition, ...]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"unable to load manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise ManifestError("manifest schema_version must be 1.0")
    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise ManifestError("manifest checks must be a non-empty list")

    checks: list[CheckDefinition] = []
    seen: set[str] = set()
    for raw in raw_checks:
        if not isinstance(raw, dict):
            raise ManifestError("each check must be an object")
        check = _parse_check(raw)
        if check.id in seen:
            raise ManifestError(f"duplicate check id: {check.id}")
        seen.add(check.id)
        checks.append(check)
    return tuple(sorted(checks, key=lambda item: (item.order, item.id)))


def _parse_check(raw: dict[str, Any]) -> CheckDefinition:
    required = (
        "id",
        "name",
        "category",
        "required",
        "areas",
        "timeout_seconds",
        "dependencies",
        "failure_classification",
        "parallel",
        "order",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise ManifestError(f"check missing fields: {', '.join(missing)}")
    command = raw.get("command")
    implementation = raw.get("implementation")
    if (command is None) == (implementation is None):
        raise ManifestError(
            f"check {raw['id']} requires exactly one command or implementation"
        )
    if command is not None and (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise ManifestError(f"check {raw['id']} command must be string array")
    timeout = raw["timeout_seconds"]
    if not isinstance(timeout, int) or timeout < 1:
        raise ManifestError(f"check {raw['id']} timeout must be positive")
    return CheckDefinition(
        id=str(raw["id"]),
        name=str(raw["name"]),
        category=str(raw["category"]),
        required=bool(raw["required"]),
        areas=tuple(str(area) for area in raw["areas"]),
        timeout_seconds=timeout,
        dependencies=tuple(str(item) for item in raw["dependencies"]),
        failure_classification=str(raw["failure_classification"]),
        parallel=bool(raw["parallel"]),
        order=int(raw["order"]),
        command=tuple(command) if command is not None else None,
        implementation=str(implementation) if implementation is not None else None,
        working_directory=(
            str(raw["working_directory"])
            if raw.get("working_directory") is not None
            else None
        ),
    )
