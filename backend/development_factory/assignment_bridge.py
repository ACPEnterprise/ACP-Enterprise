"""Prepare queue-to-Worker-Control claim envelopes without claiming work.

The existing Engineering Control / Worker Control services remain the only
durable authority for commands, leases, fencing, checkpoints, and recovery.
This module only binds a validated queue assignment to a clean machine receipt
and emits a deterministic handoff envelope for that authority to consume.
"""

from __future__ import annotations

import hashlib
import json
import re

from development_factory.coordination import (
    CoordinationError,
    CoordinationQueue,
    eligible_after_activation,
)

ENVELOPE_SCHEMA = "twelfthats.assignment-claim-envelope.v1"
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_ROLE_TO_LANE = {"LAPTOP": "LAPTOP_MASTER", "OM1": "OM1", "OM2": "OM2"}


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def queue_digest(queue: CoordinationQueue) -> str:
    return _digest(
        {
            "schema_version": queue.schema_version,
            "status": queue.status,
            "assignments": [
                {
                    "id": item.id,
                    "lane": item.lane,
                    "priority": item.priority,
                    "state": item.state,
                    "depends_on": list(item.depends_on),
                    "objective": item.objective,
                    "allowed_paths": list(item.allowed_paths),
                    "validation": list(item.validation),
                    "stop_conditions": list(item.stop_conditions),
                }
                for item in queue.assignments
            ],
        }
    )


def prepare_claim_envelope(
    queue: CoordinationQueue,
    *,
    assignment_id: str,
    inventory: dict[str, object],
    completed_assignments: tuple[str, ...] = (),
) -> dict[str, object]:
    """Create a deterministic, unclaimed envelope for existing control APIs."""
    assignment = queue.by_id.get(assignment_id)
    if assignment is None:
        raise CoordinationError(f"unknown assignment: {assignment_id}")
    role = inventory.get("role_claimed")
    lane = _ROLE_TO_LANE.get(str(role))
    if lane != assignment.lane:
        raise CoordinationError(
            f"machine role {role!r} is not authorized for assignment lane {assignment.lane}"
        )
    repository = inventory.get("repository")
    if not isinstance(repository, dict):
        raise CoordinationError("machine inventory repository evidence is missing")
    if repository.get("status_clean") is not True:
        raise CoordinationError(
            "machine repository must be clean before claim preparation"
        )
    branch = repository.get("branch")
    head = repository.get("head")
    root = repository.get("root")
    if not isinstance(branch, str) or not branch:
        raise CoordinationError("machine repository branch is missing")
    if not isinstance(head, str) or not _SHA1.fullmatch(head):
        raise CoordinationError("machine repository head is not a SHA-1")
    if not isinstance(root, str) or not root:
        raise CoordinationError("machine repository root is missing")
    host = inventory.get("host")
    hostname = (
        host.get("hostname")
        if isinstance(host, dict) and isinstance(host.get("hostname"), str)
        else "UNAVAILABLE"
    )
    if assignment_id not in eligible_after_activation(
        queue, (lane,), completed_assignments
    ):
        raise CoordinationError(
            f"assignment {assignment_id} is not eligible from supplied activation evidence"
        )
    if not assignment.allowed_paths or not assignment.validation:
        raise CoordinationError(
            f"assignment {assignment_id} has no enforceable paths or validation contract"
        )
    machine_digest = _digest(inventory)
    queue_hash = queue_digest(queue)
    idempotency_key = f"development-factory:{assignment_id}:{queue_hash[:24]}"
    return {
        "schema": ENVELOPE_SCHEMA,
        "claim_state": "PREPARED_NOT_CLAIMED",
        "assignment_id": assignment.id,
        "lane": assignment.lane,
        "priority": assignment.priority,
        "objective": assignment.objective,
        "queue_digest_sha256": queue_hash,
        "machine_inventory_digest_sha256": machine_digest,
        "machine": {
            "role": role,
            "hostname": hostname,
            "repository_root": root,
            "branch": branch,
            "head": head,
        },
        "execution_boundary": {
            "allowed_paths": list(assignment.allowed_paths),
            "validation_requirements": list(assignment.validation),
            "stop_conditions": list(assignment.stop_conditions),
        },
        "engineering_control": {
            "authority": "existing Engineering Control / Worker Control",
            "idempotency_key": idempotency_key,
            "durable_claim_required": True,
            "worker_identity_required": True,
            "lease_required": True,
            "independent_review_required": assignment.lane
            in {"OM1", "OM2", "REVIEWER"},
            "owner_approval_required": False,
        },
        "safety": {
            "claim_issued": False,
            "lease_issued": False,
            "approval_issued": False,
            "git_mutation_performed": False,
            "live_data_mutation": False,
        },
    }


__all__ = ["ENVELOPE_SCHEMA", "prepare_claim_envelope", "queue_digest"]
