from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RoadmapError(ValueError):
    pass


@dataclass(frozen=True)
class RoadmapMilestone:
    code: str
    lane: str | None
    launch_class: str | None
    engineering_status: str | None = None
    protected_integration_status: str | None = None
    beta_deployment_status: str | None = None
    owner_acceptance_status: str | None = None
    lifecycle_status: str | None = None


@dataclass(frozen=True)
class FactoryRoadmap:
    milestones: tuple[RoadmapMilestone, ...]
    digest: str


def load_roadmap(path: Path, *, digest_path: Path | None = None) -> FactoryRoadmap:
    """Load the canonical roadmap, whose YAML surface is intentionally JSON syntax."""
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise RoadmapError(
            "canonical factory roadmap is unavailable or invalid"
        ) from error
    rows = document.get("milestones") if isinstance(document, dict) else None
    if isinstance(rows, dict):
        rows = [
            dict(value, code=key) if isinstance(value, dict) else None
            for key, value in rows.items()
        ]
    if not isinstance(rows, list):
        raise RoadmapError("canonical factory roadmap must contain milestones")
    milestones: list[RoadmapMilestone] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RoadmapError("roadmap milestone must be an object")
        code = row.get("code") or row.get("id") or row.get("milestone_code")
        if not isinstance(code, str) or not code.strip() or code in seen:
            raise RoadmapError("roadmap milestone code is missing or duplicated")
        seen.add(code)
        lane = row.get("lane") or row.get("owner")
        launch_class = row.get("launch_class") or row.get("priority")
        milestones.append(
            RoadmapMilestone(
                code,
                lane if isinstance(lane, str) else None,
                launch_class if isinstance(launch_class, str) else None,
                row.get("engineering_status"),
                row.get("protected_integration_status"),
                row.get("beta_deployment_status"),
                row.get("owner_acceptance_status"),
                row.get("lifecycle_status"),
            )
        )
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    if digest_path is not None:
        try:
            expected_digest = digest_path.read_text(encoding="ascii").strip()
        except OSError as error:
            raise RoadmapError(
                "packaged factory roadmap digest is unavailable"
            ) from error
        if expected_digest != digest:
            raise RoadmapError("packaged factory roadmap digest does not match")
    return FactoryRoadmap(tuple(milestones), digest)


def safe_event_details(details: dict[str, Any]) -> dict[str, Any]:
    forbidden = {
        "secret",
        "token",
        "password",
        "credential",
        "payroll_value",
        "wage",
        "amount",
    }

    def contains_forbidden_key(value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                any(term in str(key).lower() for term in forbidden)
                or contains_forbidden_key(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(contains_forbidden_key(item) for item in value)
        return False

    if contains_forbidden_key(details):
        raise RoadmapError("factory event details contain prohibited material")
    encoded = json.dumps(details, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 16_384:
        raise RoadmapError("factory event details exceed the bounded size")
    return json.loads(encoded)
