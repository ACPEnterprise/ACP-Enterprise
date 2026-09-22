from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.platform.security.safe_output import (
    sanitize_text,
    validate_no_sensitive_fields,
)


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
    title: str | None = None
    next_admissible_action: str | None = None
    human_provider_gates: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactoryRoadmap:
    milestones: tuple[RoadmapMilestone, ...]
    operational_acceptance: tuple[OperationalAcceptanceSurface, ...]
    digest: str


@dataclass(frozen=True)
class OperationalAcceptanceSurface:
    acceptance_id: str
    surface: str
    milestone_code: str
    owner_task: str
    real_data_required: str
    current_result: str
    blocker: str
    owning_domain: str
    priority: Literal["P0", "P1", "P2", "P3"]
    status: Literal[
        "NOT_TESTED",
        "PASS",
        "DEFECT",
        "HUMAN_INPUT_REQUIRED",
        "PROVIDER_GATE",
    ]
    beta_operable: bool
    owner_accepted: bool
    evidence: tuple[str, ...]


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
    required_status_fields = (
        "engineering_status",
        "protected_integration_status",
        "beta_deployment_status",
        "owner_acceptance_status",
        "lifecycle_status",
    )
    for row in rows:
        if not isinstance(row, dict):
            raise RoadmapError("roadmap milestone must be an object")
        code = row.get("code") or row.get("id") or row.get("milestone_code")
        if not isinstance(code, str) or not code.strip() or code in seen:
            raise RoadmapError("roadmap milestone code is missing or duplicated")
        if any(
            not isinstance(row.get(field), str) or not row[field].strip()
            for field in required_status_fields
        ):
            raise RoadmapError(
                f"roadmap milestone {code} is missing an authoritative status"
            )
        seen.add(code)
        lane = row.get("lane") or row.get("owner")
        launch_class = row.get("launch_class") or row.get("priority")
        successor_contract = row.get("successor_supersession", {})
        if not isinstance(successor_contract, dict):
            raise RoadmapError(
                f"roadmap milestone {code} has an invalid supersession contract"
            )
        supersedes = successor_contract.get("supersedes", [])
        if not isinstance(supersedes, list) or any(
            not isinstance(item, str) or not item.strip() for item in supersedes
        ):
            raise RoadmapError(
                f"roadmap milestone {code} has an invalid supersedes list"
            )
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
                row.get("title"),
                row.get("next_admissible_action"),
                tuple(row.get("human_provider_gates", ())),
                tuple(row.get("prerequisites", ())),
                tuple(supersedes),
            )
        )
    codes = {item.code for item in milestones}
    for milestone in milestones:
        missing = sorted(set(milestone.prerequisites) - codes)
        if missing:
            raise RoadmapError(
                f"roadmap milestone {milestone.code} has unknown prerequisites: "
                + ", ".join(missing)
            )

    visiting: set[str] = set()
    visited: set[str] = set()
    graph = {item.code: item.prerequisites for item in milestones}

    def visit(code: str) -> None:
        if code in visited:
            return
        if code in visiting:
            raise RoadmapError("canonical factory roadmap dependency graph is cyclic")
        visiting.add(code)
        for dependency in graph[code]:
            visit(dependency)
        visiting.remove(code)
        visited.add(code)

    for code in graph:
        visit(code)

    acceptance_document = document.get("real_operational_acceptance", {})
    if acceptance_document is None:
        acceptance_document = {}
    if not isinstance(acceptance_document, dict):
        raise RoadmapError("real operational acceptance must be an object")
    acceptance_rows = acceptance_document.get("surfaces", [])
    if not isinstance(acceptance_rows, list):
        raise RoadmapError("real operational acceptance surfaces must be a list")
    acceptance: list[OperationalAcceptanceSurface] = []
    seen_acceptance_ids: set[str] = set()
    seen_surfaces: set[str] = set()
    accepted_statuses = {
        "NOT_TESTED",
        "PASS",
        "DEFECT",
        "HUMAN_INPUT_REQUIRED",
        "PROVIDER_GATE",
    }
    for row in acceptance_rows:
        if not isinstance(row, dict):
            raise RoadmapError("operational acceptance surface must be an object")
        required_strings = (
            "id",
            "surface",
            "milestone_id",
            "owner_task",
            "real_data_required",
            "current_result",
            "blocker",
            "owning_domain",
            "priority",
            "status",
        )
        if any(
            not isinstance(row.get(field), str) or not row[field].strip()
            for field in required_strings
        ):
            raise RoadmapError(
                "operational acceptance surface is missing a required field"
            )
        if row["id"] in seen_acceptance_ids or row["surface"] in seen_surfaces:
            raise RoadmapError("operational acceptance identity is duplicated")
        if row["milestone_id"] not in codes:
            raise RoadmapError("operational acceptance milestone is unknown")
        if row["status"] not in accepted_statuses:
            raise RoadmapError("operational acceptance status is invalid")
        if row["priority"] not in {"P0", "P1", "P2", "P3"}:
            raise RoadmapError("operational acceptance priority is invalid")
        if not isinstance(row.get("beta_operable"), bool) or not isinstance(
            row.get("owner_accepted"), bool
        ):
            raise RoadmapError("operational acceptance truth flags are required")
        if row["status"] == "PASS":
            if not row["beta_operable"] or not row["owner_accepted"]:
                raise RoadmapError("operational acceptance PASS requires owner proof")
        elif row["beta_operable"] or row["owner_accepted"]:
            raise RoadmapError(
                "non-PASS operational acceptance cannot claim completion"
            )
        evidence = row.get("evidence", [])
        if not isinstance(evidence, list) or any(
            not isinstance(item, str) or not item.strip() for item in evidence
        ):
            raise RoadmapError("operational acceptance evidence is invalid")
        seen_acceptance_ids.add(row["id"])
        seen_surfaces.add(row["surface"])
        acceptance.append(
            OperationalAcceptanceSurface(
                acceptance_id=row["id"],
                surface=row["surface"],
                milestone_code=row["milestone_id"],
                owner_task=row["owner_task"],
                real_data_required=row["real_data_required"],
                current_result=row["current_result"],
                blocker=row["blocker"],
                owning_domain=row["owning_domain"],
                priority=row["priority"],
                status=row["status"],
                beta_operable=row["beta_operable"],
                owner_accepted=row["owner_accepted"],
                evidence=tuple(evidence),
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
    return FactoryRoadmap(tuple(milestones), tuple(acceptance), digest)


def safe_event_details(details: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "count",
        "defect_id",
        "digest",
        "gate_id",
        "handoff_id",
        "reason_code",
        "result",
        "status",
        "action",
        "why_blocked",
        "workflow",
        "estimated_owner_minutes",
        "resume_action",
        "gate_type",
        "priority",
        "source_kind",
        "source_id",
        "evidence",
        "engineering_prerequisites_resolved",
    }

    def contains_forbidden_key(value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                str(key) not in allowed or contains_forbidden_key(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(contains_forbidden_key(item) for item in value)
        if isinstance(value, str):
            return sanitize_text(value) != value
        return False

    try:
        validate_no_sensitive_fields(details, boundary="Factory Control event details")
    except ValueError as error:
        raise RoadmapError(
            "factory event details contain prohibited material"
        ) from error
    if contains_forbidden_key(details):
        raise RoadmapError("factory event details contain prohibited material")
    encoded = json.dumps(details, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 16_384:
        raise RoadmapError("factory event details exceed the bounded size")
    return json.loads(encoded)
