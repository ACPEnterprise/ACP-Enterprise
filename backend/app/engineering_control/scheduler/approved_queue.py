"""Reviewed, machine-readable owner-approved headless factory queue."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class QueueError(ValueError):
    pass


class QueueModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovedWork(QueueModel):
    milestone_id: str = Field(pattern=r"^[A-Z][A-Z0-9_.-]{4,119}$")
    capacity_identity: Literal["OM1", "OM2", "MIG", "ECO", "LAP"]
    instruction: str = Field(min_length=20, max_length=12_000)
    allowed_paths: tuple[str, ...] = Field(min_length=1)
    validation_requirements: tuple[str, ...] = Field(min_length=1)
    requested_code_changes: bool
    queue_state: Literal[
        "AUTHORITATIVE", "READY", "BLOCKED_DEPENDENCY", "ENTERPRISE_REVIEW_REQUIRED"
    ]
    execution_mode: Literal["none", "repository_only", "preview_gated"]
    hard_boundary_operations: tuple[str, ...]
    dependencies: tuple[str, ...]
    successor_ids: tuple[str, ...]
    authoritative_commit_sha: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{40}$"
    )
    candidate_reference: str | None = None


class ApprovedFactoryQueue(QueueModel):
    schema_version: Literal["1.0"]
    queue_id: Literal["ACP.72H.2026-09-03"]
    owner_authorization_reference: Literal["ACP ENTERPRISE — 72-HOUR LAUNCH & OPERATIONS FACTORY"]
    authoritative_repository_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    items: tuple[ApprovedWork, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def queue_fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_approved_factory_queue() -> ApprovedFactoryQueue:
    path = files("app.engineering_control.scheduler").joinpath(
        "owner-approved-queue.2026-09-03.v1.json"
    )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fingerprint = raw.pop("fingerprint")
    except (OSError, json.JSONDecodeError, KeyError, AttributeError) as error:
        raise QueueError("approved queue provenance cannot be established") from error
    if fingerprint != queue_fingerprint(raw):
        raise QueueError("approved queue fingerprint mismatch")
    try:
        queue = ApprovedFactoryQueue.model_validate(
            {**raw, "fingerprint": fingerprint}
        )
    except ValidationError as error:
        raise QueueError("approved queue is invalid") from error
    ids = [item.milestone_id for item in queue.items]
    if len(ids) != len(set(ids)):
        raise QueueError("approved queue contains duplicate milestone identity")
    known = set(ids)
    if any(set(item.successor_ids) - known for item in queue.items):
        raise QueueError("approved queue references an unknown successor")
    for item in queue.items:
        if item.queue_state == "AUTHORITATIVE" and not item.authoritative_commit_sha:
            raise QueueError("authoritative work requires commit evidence")
        if item.queue_state == "READY" and (
            item.execution_mode != "repository_only" or item.hard_boundary_operations
        ):
            raise QueueError("ready headless work must be repository-only")
        if (set(item.dependencies) | set(item.successor_ids)) - known:
            raise QueueError("approved queue references an unknown dependency")
    return queue


__all__ = ["ApprovedFactoryQueue", "ApprovedWork", "QueueError", "load_approved_factory_queue"]
