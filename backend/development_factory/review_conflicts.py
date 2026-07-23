from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from development_factory.lia_contract import WorkerAssignment
from development_factory.lia_planner import ExecutionPlan


@dataclass(frozen=True)
class FileConflict:
    left_task_id: str
    right_task_id: str
    left_path: str
    right_path: str
    classification: str
    rationale: str


@dataclass(frozen=True)
class ResourceConflict:
    left_task_id: str
    right_task_id: str
    resource_type: str
    resource_id: str
    classification: str
    rationale: str


@dataclass(frozen=True)
class ValidationSummary:
    task_id: str
    required: tuple[str, ...]
    executed: tuple[str, ...]
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    missing: tuple[str, ...]
    redacted: bool


def detect_file_conflicts(
    changed_files: dict[str, tuple[str, ...]],
    workers: dict[str, WorkerAssignment],
) -> tuple[FileConflict, ...]:
    conflicts: list[FileConflict] = []
    task_ids = sorted(changed_files)
    for index, left_id in enumerate(task_ids):
        for right_id in task_ids[index + 1 :]:
            dependent = (
                left_id in workers[right_id].depends_on
                or right_id in workers[left_id].depends_on
            )
            for left_path in changed_files[left_id]:
                for right_path in changed_files[right_id]:
                    kind = _path_conflict(left_path, right_path)
                    if kind is None:
                        continue
                    classification = (
                        "ordered_dependency" if dependent else "prohibited_overlap"
                    )
                    conflicts.append(
                        FileConflict(
                            left_id,
                            right_id,
                            left_path,
                            right_path,
                            classification,
                            f"{kind}; automatic resolution is prohibited",
                        )
                    )
    return tuple(
        sorted(
            conflicts,
            key=lambda item: (
                item.left_task_id,
                item.right_task_id,
                item.left_path.casefold(),
                item.right_path.casefold(),
            ),
        )
    )


def detect_resource_conflicts(
    workers: tuple[WorkerAssignment, ...],
) -> tuple[ResourceConflict, ...]:
    conflicts: list[ResourceConflict] = []
    for index, left in enumerate(workers):
        for right in workers[index + 1 :]:
            for left_claim in left.shared_resources:
                for right_claim in right.shared_resources:
                    if (
                        left_claim.resource_type != right_claim.resource_type
                        or left_claim.resource_id != right_claim.resource_id
                    ):
                        continue
                    dependent = (
                        left.task.task_id in right.depends_on
                        or right.task.task_id in left.depends_on
                    )
                    if "exclusive" in {left_claim.mode, right_claim.mode}:
                        classification = "prohibited_overlap"
                    elif dependent:
                        classification = "ordered_dependency"
                    else:
                        classification = "review_order_required"
                    conflicts.append(
                        ResourceConflict(
                            left.task.task_id,
                            right.task.task_id,
                            left_claim.resource_type,
                            left_claim.resource_id,
                            classification,
                            "typed resource is claimed by multiple workers",
                        )
                    )
    return tuple(
        sorted(
            conflicts,
            key=lambda item: (
                item.resource_type,
                item.resource_id,
                item.left_task_id,
                item.right_task_id,
            ),
        )
    )


def consolidate_validation(
    task_id: str, required: tuple[str, ...], payload: dict[str, object]
) -> ValidationSummary:
    raw = payload.get("validation_results")
    if not isinstance(raw, list):
        raw = []
    executed: list[str] = []
    passed: list[str] = []
    failed: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("selection"), str):
            continue
        selection = item["selection"]
        executed.append(selection)
        if (
            item.get("exit_classification") == "passed"
            and item.get("blocks_completion") is False
        ):
            passed.append(selection)
        else:
            failed.append(selection)
    missing = tuple(sorted(set(required) - set(executed)))
    return ValidationSummary(
        task_id=task_id,
        required=required,
        executed=tuple(executed),
        passed=tuple(passed),
        failed=tuple(failed),
        missing=missing,
        redacted=payload.get("secret_redaction_result") == "applied",
    )


def deterministic_review_order(
    plan: ExecutionPlan,
    workers: dict[str, WorkerAssignment],
    classifications: dict[str, str],
) -> tuple[tuple[str, str], ...]:
    wave_by_task = {
        task_id: wave.number for wave in plan.waves for task_id in wave.task_ids
    }

    def priority(task_id: str) -> tuple[int, int, str]:
        worker = workers[task_id]
        classification = classifications[task_id]
        if classification.startswith("blocked_") or classification in {
            "failed",
            "stale",
            "contradictory_record",
            "missing_record",
        }:
            group = 0
        elif any(
            claim.resource_type in {"security_surface", "shared_schema", "migration"}
            for claim in worker.shared_resources
        ):
            group = 1
        elif worker.role_id == "forge":
            group = 2
        elif worker.role_id == "atlas":
            group = 3
        elif worker.role_id == "nova":
            group = 4
        elif worker.role_id == "scout":
            group = 5
        else:
            group = 6
        return group, wave_by_task[task_id], task_id

    ordered = sorted(workers, key=priority)
    return tuple(
        (
            task_id,
            (
                "blocker or escalation first"
                if priority(task_id)[0] == 0
                else f"wave {wave_by_task[task_id]} and role/resource priority"
            ),
        )
        for task_id in ordered
    )


def migration_schema_findings(
    changed_files: dict[str, tuple[str, ...]],
    workers: dict[str, WorkerAssignment],
) -> tuple[str, ...]:
    findings: list[str] = []
    migration_owners: list[str] = []
    for task_id, paths in changed_files.items():
        for path in paths:
            lower = path.lower()
            if "alembic/versions/" in lower:
                migration_owners.append(task_id)
                if not _has_claim(workers[task_id], {"migration", "database"}):
                    findings.append(
                        f"{task_id}: migration changed without migration ownership"
                    )
            if lower.endswith(("schema.json", "models.py")) and not _has_claim(
                workers[task_id], {"shared_schema", "database", "integration_surface"}
            ):
                findings.append(
                    f"{task_id}: schema or persistence surface changed without claim"
                )
    if len(set(migration_owners)) > 1:
        findings.append(
            "multiple migration owners require deterministic migration-chain review"
        )
    return tuple(sorted(set(findings)))


def security_architecture_findings(
    changed_files: dict[str, tuple[str, ...]],
    workers: dict[str, WorkerAssignment],
    payloads: dict[str, dict[str, Any]],
) -> tuple[str, ...]:
    findings: list[str] = []
    sensitive_tokens = (
        "auth",
        "permission",
        "security",
        "tenant",
        "infrastructure",
        "deploy",
        "workflow",
    )
    for task_id, paths in changed_files.items():
        worker = workers[task_id]
        for path in paths:
            lowered = path.lower()
            if any(token in lowered for token in sensitive_tokens):
                if not _has_claim(worker, {"security_surface", "integration_surface"}):
                    findings.append(
                        f"{task_id}: sensitive surface changed without "
                        f"explicit claim: {path}"
                    )
                else:
                    findings.append(
                        f"{task_id}: security-sensitive surface requires "
                        f"explicit owner review: {path}"
                    )
        payload = payloads[task_id]
        for escalation in payload.get("escalations", []):
            if isinstance(escalation, str):
                findings.append(f"{task_id}: {escalation}")
        if payload.get("secret_redaction_result") != "applied":
            findings.append(f"{task_id}: worker record redaction evidence is missing")
    return tuple(sorted(set(findings)))


def _path_conflict(left: str, right: str) -> str | None:
    if left.casefold() == right.casefold():
        return "same-file or case-normalization collision"
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shortest = min(len(left_parts), len(right_parts))
    if tuple(part.casefold() for part in left_parts[:shortest]) == tuple(
        part.casefold() for part in right_parts[:shortest]
    ):
        return "parent/child or file/directory collision"
    return None


def _has_claim(worker: WorkerAssignment, types: set[str]) -> bool:
    return any(claim.resource_type in types for claim in worker.shared_resources)
