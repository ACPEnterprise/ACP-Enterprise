from __future__ import annotations

import hashlib
import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROVENANCE_VERSION = "1.0"


class ProvenanceError(ValueError):
    pass


@dataclass(frozen=True)
class ContentDigest:
    path: str
    state: str
    sha256: str


@dataclass(frozen=True)
class WorkerProvenance:
    schema_version: str
    assignment_id: str
    supervisory_contract_digest: str
    workspace_metadata_reference: str
    workspace_metadata_digest: str
    operations_manifest_digest: str
    validation_plan_id: str
    validation_selections: tuple[str, ...]
    validation_plan_digest: str
    validation_evidence_reference: str
    validation_evidence_digest: str
    output_manifest_digest: str
    output_files: tuple[ContentDigest, ...]
    declared_allowed_paths: tuple[str, ...]
    declared_operation_ids: tuple[str, ...]
    artifact_references: tuple[str, ...]
    approval_state: str
    integration_state: str
    cleanup_state: str
    manifest_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_digest(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def content_manifest(
    workspace: Path, paths: tuple[str, ...]
) -> tuple[ContentDigest, ...]:
    evidence: list[ContentDigest] = []
    for relative in sorted(set(paths)):
        candidate = workspace / relative
        if candidate.is_file() and not candidate.is_symlink():
            evidence.append(
                ContentDigest(
                    relative,
                    "present",
                    hashlib.sha256(candidate.read_bytes()).hexdigest(),
                )
            )
        elif not candidate.exists():
            evidence.append(ContentDigest(relative, "deleted", canonical_digest(None)))
        else:
            raise ProvenanceError(
                f"output evidence is not a regular workspace file: {relative}"
            )
    return tuple(evidence)


def output_manifest_digest(items: tuple[ContentDigest, ...]) -> str:
    return canonical_digest([asdict(item) for item in items])


def build_worker_provenance(
    *,
    assignment_id: str,
    supervisory_contract: dict[str, Any],
    workspace_metadata: dict[str, Any],
    operations_manifest: dict[str, Any],
    validation_results: tuple[dict[str, Any], ...],
    output_files: tuple[ContentDigest, ...],
    declared_allowed_paths: tuple[str, ...],
    execution_id: str,
    workspace_id: str,
) -> WorkerProvenance:
    validation_selections = tuple(operations_manifest["validation_selections"])
    validation_plan = {
        "assignment_id": assignment_id,
        "selections": validation_selections,
    }
    body: dict[str, Any] = {
        "schema_version": PROVENANCE_VERSION,
        "assignment_id": assignment_id,
        "supervisory_contract_digest": canonical_digest(supervisory_contract),
        "workspace_metadata_reference": f"workspace-metadata:{workspace_id}",
        "workspace_metadata_digest": canonical_digest(workspace_metadata),
        "operations_manifest_digest": canonical_digest(
            operations_manifest["operations"]
        ),
        "validation_plan_id": f"{execution_id}:validation-plan",
        "validation_selections": validation_selections,
        "validation_plan_digest": canonical_digest(validation_plan),
        "validation_evidence_reference": (
            f"worker-execution:{execution_id}#validation_results"
        ),
        "validation_evidence_digest": canonical_digest(validation_results),
        "output_manifest_digest": output_manifest_digest(output_files),
        "output_files": tuple(output_files),
        "declared_allowed_paths": tuple(sorted(set(declared_allowed_paths))),
        "declared_operation_ids": tuple(
            item["operation_id"] for item in operations_manifest["operations"]
        ),
        "artifact_references": (
            f"worker-execution:{execution_id}.json",
            f"worker-execution:{execution_id}.md",
        ),
        "approval_state": "owner_review_required",
        "integration_state": "not_integrated",
        "cleanup_state": "workspace_retained",
    }
    digest = canonical_digest(_serializable(body))
    return WorkerProvenance(**body, manifest_digest=digest)


def validate_worker_provenance(payload: dict[str, Any]) -> tuple[str, ...]:
    value = payload.get("provenance")
    if not isinstance(value, dict):
        return ("required provenance manifest is missing",)
    required = set(WorkerProvenance.__dataclass_fields__)
    if value.keys() != required:
        return ("provenance manifest fields are invalid",)
    findings: list[str] = []
    if value.get("schema_version") != PROVENANCE_VERSION:
        findings.append("provenance schema version is invalid")
    comparisons = (
        ("assignment_id", payload.get("worker_task_id")),
        (
            "workspace_metadata_reference",
            f"workspace-metadata:{payload.get('workspace_id')}",
        ),
        (
            "validation_evidence_reference",
            f"worker-execution:{payload.get('execution_id')}#validation_results",
        ),
        ("approval_state", "owner_review_required"),
        ("integration_state", "not_integrated"),
        ("cleanup_state", "workspace_retained"),
    )
    findings.extend(
        f"provenance {field} mismatch"
        for field, expected in comparisons
        if value.get(field) != expected
    )
    operations = payload.get("requested_operations")
    validation = payload.get("validation_results")
    if value.get("validation_evidence_digest") != canonical_digest(validation):
        findings.append("validation evidence digest mismatch")
    validation_selections = (
        tuple(item.get("selection") for item in validation)
        if isinstance(validation, list)
        and all(isinstance(item, dict) for item in validation)
        else ()
    )
    declared_validation = value.get("validation_selections")
    if not isinstance(declared_validation, list) or not set(
        validation_selections
    ) <= set(declared_validation):
        findings.append("validation selections do not match evidence")
    validation_plan = {
        "assignment_id": payload.get("worker_task_id"),
        "selections": value.get("validation_selections"),
    }
    if value.get("validation_plan_digest") != canonical_digest(validation_plan):
        findings.append("validation plan digest mismatch")
    operation_ids = (
        tuple(item.get("operation_id") for item in operations)
        if isinstance(operations, list)
        and all(isinstance(item, dict) for item in operations)
        else ()
    )
    if tuple(value.get("declared_operation_ids", ())) != operation_ids:
        findings.append("declared operation identifiers mismatch")
    if value.get("operations_manifest_digest") != canonical_digest(operations):
        findings.append("operations manifest digest mismatch")
    output_files = value.get("output_files")
    if not isinstance(output_files, list):
        findings.append("output content manifest is invalid")
    elif value.get("output_manifest_digest") != canonical_digest(output_files):
        findings.append("output manifest digest mismatch")
    else:
        allowed = value.get("declared_allowed_paths")
        if not isinstance(allowed, list) or not allowed:
            findings.append("declared evidence boundary is missing")
        elif any(
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not any(
                fnmatch.fnmatchcase(item["path"], pattern)
                for pattern in allowed
                if isinstance(pattern, str)
            )
            for item in output_files
        ):
            findings.append("output evidence exceeds declared boundary")
    manifest_body = {
        key: item for key, item in value.items() if key != "manifest_digest"
    }
    if value.get("manifest_digest") != canonical_digest(manifest_body):
        findings.append("provenance manifest digest mismatch")
    expected_artifacts = [
        f"worker-execution:{payload.get('execution_id')}.json",
        f"worker-execution:{payload.get('execution_id')}.md",
    ]
    if value.get("artifact_references") != expected_artifacts:
        findings.append("provenance artifact references are missing")
    return tuple(findings)


def _serializable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_serializable(item) for item in value]
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serializable(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return _serializable(asdict(value))
    return value
