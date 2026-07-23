from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from development_factory.reports import redact
from development_factory.review_conflicts import (
    FileConflict,
    ResourceConflict,
    ValidationSummary,
)


CONSOLIDATION_INPUT_VERSION = "1.0"
OWNER_REVIEW_VERSION = "1.0"
OWNER_DECISION_VERSION = "1.0"
REVIEW_SECRET_PATTERN = re.compile(
    r"(?i)([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY|ACCESS_KEY)"
    r"[A-Z0-9_]*\s*[:=]\s*)([^\s,\"'}]+)"
)


class ReviewRecordError(ValueError):
    pass


@dataclass(frozen=True)
class ReviewPolicy:
    require_all_workers: bool
    allow_incomplete_downstream_review: bool
    security_sensitive_owner_review: bool


@dataclass(frozen=True)
class ConsolidationInput:
    schema_version: str
    review_id: str
    supervisory_run_id: str
    parent_milestone: str
    parent_objective: str
    approved_branch: str
    approved_starting_sha: str
    supervisory_contract_digest: str
    included_worker_task_ids: tuple[str, ...]
    worker_records: tuple[str, ...]
    required_execution_waves: tuple[tuple[str, ...], ...]
    required_dependency_evidence: bool
    required_validation_evidence: tuple[str, ...]
    review_policy: ReviewPolicy
    conflict_policy: str
    stop_policy: tuple[str, ...]
    required_owner_decision_fields: tuple[str, ...]


@dataclass(frozen=True)
class WorkerReview:
    task_id: str
    worker_id: str
    execution_id: str | None
    record_digest: str | None
    classification: str
    rationale: tuple[str, ...]
    workspace_id: str
    workspace_path: str
    changed_files: tuple[str, ...]
    provenance_findings: tuple[str, ...]
    validation: ValidationSummary | None


@dataclass(frozen=True)
class ReviewActionAudit:
    worker_execution_performed_by_consolidator: bool = False
    files_modified_by_consolidator: bool = False
    staged_by_factory: bool = False
    committed_by_factory: bool = False
    cherry_picked_by_factory: bool = False
    merged_by_factory: bool = False
    pushed_by_factory: bool = False
    deployed_by_factory: bool = False
    workspace_deleted_by_factory: bool = False
    branch_deleted_by_factory: bool = False


@dataclass(frozen=True)
class ConsolidatedOwnerReview:
    schema_version: str
    review_id: str
    supervisory_run_id: str
    parent_milestone: str
    parent_objective: str
    approved_branch: str
    approved_starting_sha: str
    supervisory_contract_digest: str
    included_worker_records: tuple[tuple[str, str], ...]
    excluded_or_missing_workers: tuple[str, ...]
    execution_waves: tuple[tuple[str, ...], ...]
    dependency_status: tuple[tuple[str, str], ...]
    worker_reviews: tuple[WorkerReview, ...]
    workspace_provenance_findings: tuple[str, ...]
    verified_changed_file_summaries: tuple[tuple[str, tuple[str, ...]], ...]
    file_conflicts: tuple[FileConflict, ...]
    resource_conflicts: tuple[ResourceConflict, ...]
    migration_schema_findings: tuple[str, ...]
    architecture_security_findings: tuple[str, ...]
    validation_summaries: tuple[ValidationSummary, ...]
    aggregate_revalidation_requirements: tuple[str, ...]
    recommended_review_order: tuple[tuple[str, str], ...]
    advisory_future_integration_order: tuple[tuple[str, str], ...]
    rejected_or_noneligible_outputs: tuple[str, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]
    owner_decisions_required: tuple[str, ...]
    recorded_owner_decisions: tuple[str, ...]
    secret_redaction_result: str
    action_audit: ReviewActionAudit
    state_history: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return _sanitize(asdict(self))


@dataclass(frozen=True)
class OwnerDecision:
    schema_version: str
    decision_id: str
    supervisory_run_id: str
    review_id: str
    worker_task_id: str | None
    decision_type: str
    decision_status: str
    rationale: str
    timestamp: str
    review_digest: str
    permits_further_planning_only: bool
    privileged_action_audit: ReviewActionAudit

    def to_dict(self) -> dict[str, Any]:
        return _sanitize(asdict(self))


def load_consolidation_input(path: Path) -> ConsolidationInput:
    payload = _load_object(path, "consolidation input")
    expected = {
        "schema_version",
        "review_id",
        "supervisory_run_id",
        "parent_milestone",
        "parent_objective",
        "approved_repository",
        "supervisory_contract_digest",
        "included_worker_task_ids",
        "worker_records",
        "required_execution_waves",
        "required_dependency_evidence",
        "required_validation_evidence",
        "review_policy",
        "conflict_policy",
        "stop_policy",
        "required_owner_decision_fields",
    }
    _exact(payload, expected, "consolidation input")
    if payload["schema_version"] != CONSOLIDATION_INPUT_VERSION:
        raise ReviewRecordError("consolidation input schema version is invalid")
    repository = _object(payload["approved_repository"], "approved_repository")
    _exact(repository, {"branch", "starting_sha"}, "approved_repository")
    policy = _object(payload["review_policy"], "review_policy")
    policy_fields = {
        "require_all_workers",
        "allow_incomplete_downstream_review",
        "security_sensitive_owner_review",
    }
    _exact(policy, policy_fields, "review_policy")
    if not all(isinstance(policy[field], bool) for field in policy_fields):
        raise ReviewRecordError("review policy values must be booleans")
    waves_value = payload["required_execution_waves"]
    if not isinstance(waves_value, list) or not all(
        isinstance(wave, list) for wave in waves_value
    ):
        raise ReviewRecordError("required execution waves must be an array of arrays")
    waves = tuple(
        _strings(wave, "execution wave", allow_empty=False) for wave in waves_value
    )
    return ConsolidationInput(
        schema_version=CONSOLIDATION_INPUT_VERSION,
        review_id=_nonblank(payload["review_id"], "review_id"),
        supervisory_run_id=_nonblank(
            payload["supervisory_run_id"], "supervisory_run_id"
        ),
        parent_milestone=_nonblank(payload["parent_milestone"], "parent_milestone"),
        parent_objective=_nonblank(payload["parent_objective"], "parent_objective"),
        approved_branch=_nonblank(repository["branch"], "branch"),
        approved_starting_sha=_sha(repository["starting_sha"], "starting_sha"),
        supervisory_contract_digest=_sha(
            payload["supervisory_contract_digest"], "supervisory_contract_digest"
        ),
        included_worker_task_ids=_strings(
            payload["included_worker_task_ids"], "included_worker_task_ids"
        ),
        worker_records=_strings(
            payload["worker_records"], "worker_records", allow_empty=True
        ),
        required_execution_waves=waves,
        required_dependency_evidence=_boolean(
            payload["required_dependency_evidence"],
            "required_dependency_evidence",
        ),
        required_validation_evidence=_strings(
            payload["required_validation_evidence"],
            "required_validation_evidence",
        ),
        review_policy=ReviewPolicy(**policy),
        conflict_policy=_literal(
            payload["conflict_policy"], "conflict_policy", {"fail_closed"}
        ),
        stop_policy=_strings(payload["stop_policy"], "stop_policy"),
        required_owner_decision_fields=_strings(
            payload["required_owner_decision_fields"],
            "required_owner_decision_fields",
        ),
    )


def load_owner_decision(path: Path) -> OwnerDecision:
    payload = _load_object(path, "owner decision")
    expected = {
        "schema_version",
        "decision_id",
        "supervisory_run_id",
        "review_id",
        "worker_task_id",
        "decision_type",
        "decision_status",
        "rationale",
        "timestamp",
        "review_digest",
        "permits_further_planning_only",
        "privileged_action_audit",
    }
    _exact(payload, expected, "owner decision")
    if payload["schema_version"] != OWNER_DECISION_VERSION:
        raise ReviewRecordError("owner decision schema version is invalid")
    decision_types = {
        "accept_for_continued_review",
        "reject_worker_output",
        "request_remediation",
        "request_reexecution",
        "resolve_scope_ambiguity",
        "resolve_resource_ownership",
        "require_additional_validation",
        "cancel_dependent_work",
        "preserve_workspace",
        "cleanup_planning_only",
    }
    audit = _false_audit(payload["privileged_action_audit"])
    worker_task = payload["worker_task_id"]
    if worker_task is not None and not isinstance(worker_task, str):
        raise ReviewRecordError("worker_task_id must be string or null")
    return OwnerDecision(
        schema_version=OWNER_DECISION_VERSION,
        decision_id=_nonblank(payload["decision_id"], "decision_id"),
        supervisory_run_id=_nonblank(
            payload["supervisory_run_id"], "supervisory_run_id"
        ),
        review_id=_nonblank(payload["review_id"], "review_id"),
        worker_task_id=worker_task,
        decision_type=_literal(
            payload["decision_type"], "decision_type", decision_types
        ),
        decision_status=_literal(
            payload["decision_status"],
            "decision_status",
            {"recorded", "rejected", "cancelled"},
        ),
        rationale=_nonblank(payload["rationale"], "rationale"),
        timestamp=_nonblank(payload["timestamp"], "timestamp"),
        review_digest=_sha(payload["review_digest"], "review_digest"),
        permits_further_planning_only=_boolean(
            payload["permits_further_planning_only"],
            "permits_further_planning_only",
        ),
        privileged_action_audit=audit,
    )


def write_owner_review(
    review: ConsolidatedOwnerReview, output_directory: Path
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / f"{review.review_id}.json"
    markdown_path = output_directory / f"{review.review_id}.md"
    with json_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(review.to_dict(), indent=2, sort_keys=True) + "\n")
    try:
        with markdown_path.open("x", encoding="utf-8") as stream:
            stream.write(render_owner_review_markdown(review))
    except BaseException:
        json_path.unlink(missing_ok=True)
        raise
    return json_path, markdown_path


def write_owner_decision(decision: OwnerDecision, output_directory: Path) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / f"{decision.decision_id}.json"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(decision.to_dict(), indent=2, sort_keys=True) + "\n")
    return path


def render_owner_review_markdown(review: ConsolidatedOwnerReview) -> str:
    def bullets(values: tuple[str, ...]) -> list[str]:
        return [f"- {redact(value)}" for value in values] or ["- None."]

    return "\n".join(
        [
            "# LIA Consolidated Owner Review",
            "",
            f"- Review: `{review.review_id}`",
            f"- Milestone: {redact(review.parent_milestone)}",
            f"- Starting SHA: `{review.approved_starting_sha}`",
            "- Status: owner review required",
            "",
            "## What happened",
            "",
            f"- {len(review.worker_reviews)} worker result(s) were inspected.",
            "- Workspaces and records were verified without modifying them.",
            "",
            "## Worker results",
            "",
            *[
                f"- `{item.task_id}`: `{item.classification}`"
                for item in review.worker_reviews
            ],
            "",
            "## Blockers and conflicts",
            "",
            *bullets(
                tuple(
                    (
                        *review.blockers,
                        *review.workspace_provenance_findings,
                        *review.migration_schema_findings,
                        *review.architecture_security_findings,
                    )
                )
            ),
            "",
            "## Review first",
            "",
            *[
                f"- `{task_id}` — {redact(rationale)}"
                for task_id, rationale in review.recommended_review_order
            ],
            "",
            "## Advisory future integration",
            "",
            *[
                f"- `{task_id}` — {redact(recommendation)}"
                for task_id, recommendation in review.advisory_future_integration_order
            ],
            "",
            "## Owner decisions required",
            "",
            *[f"- [ ] {redact(value)}" for value in review.owner_decisions_required],
            "",
            "## What LIA did not do",
            "",
            "- LIA did not execute workers or modify files.",
            "- LIA did not stage, commit, cherry-pick, merge, push, or deploy.",
            "- LIA did not remove workspaces or delete branches.",
            "",
        ]
    )


def canonical_digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _false_audit(value: object) -> ReviewActionAudit:
    payload = _object(value, "privileged_action_audit")
    expected = set(ReviewActionAudit.__dataclass_fields__)
    _exact(payload, expected, "privileged_action_audit")
    if any(item is not False for item in payload.values()):
        raise ReviewRecordError("owner decision cannot contain privileged actions")
    return ReviewActionAudit()


def _load_object(path: Path, field: str) -> dict[str, Any]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewRecordError(f"unable to load {field}: {exc}") from exc
    return _object(value, field)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewRecordError(f"{field} must be an object")
    return value


def _exact(value: dict[str, Any], expected: set[str], field: str) -> None:
    if value.keys() != expected:
        raise ReviewRecordError(f"{field} fields are invalid")


def _strings(
    value: object, field: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ReviewRecordError(f"{field} must be a string array")
    result = tuple(item.strip() for item in value)
    if not allow_empty and not result:
        raise ReviewRecordError(f"{field} cannot be empty")
    if len(result) != len(set(result)):
        raise ReviewRecordError(f"{field} cannot contain duplicates")
    return result


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewRecordError(f"{field} must be nonblank")
    return value.strip()


def _sha(value: object, field: str) -> str:
    text = _nonblank(value, field)
    pattern = r"[0-9a-f]{64}" if field.endswith("digest") else r"[0-9a-f]{40}"
    if not re.fullmatch(pattern, text):
        raise ReviewRecordError(f"{field} has invalid format")
    return text


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ReviewRecordError(f"{field} must be boolean")
    return value


def _literal(value: object, field: str, allowed: set[str]) -> str:
    text = _nonblank(value, field)
    if text not in allowed:
        raise ReviewRecordError(f"{field} is invalid")
    return text


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return REVIEW_SECRET_PATTERN.sub(
            lambda match: f"{match.group(1)}[REDACTED]",
            redact(value),
        )
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value
