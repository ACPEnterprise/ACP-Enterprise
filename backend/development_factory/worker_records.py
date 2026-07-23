from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from development_factory.execution_adapters import OperationResult, WorkerOperation
from development_factory.reports import redact


WORKER_RECORD_VERSION = "1.0"
WORKER_SECRET_PATTERN = re.compile(
    r"(?i)([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY|ACCESS_KEY)"
    r"[A-Z0-9_]*\s*[:=]\s*)([^\s,\"'}]+)"
)


@dataclass(frozen=True)
class WorkerActionAudit:
    staged_by_factory: bool = False
    committed_by_factory: bool = False
    pushed_by_factory: bool = False
    merged_by_factory: bool = False
    deployed_by_factory: bool = False
    workspace_deleted_by_factory: bool = False


@dataclass(frozen=True)
class WorkerValidationResult:
    selection: str
    started_at: str
    completed_at: str
    result: str
    exit_classification: str
    concise_output: str
    required: bool
    blocks_completion: bool


@dataclass(frozen=True)
class WorkerExecutionRecord:
    schema_version: str
    execution_id: str
    supervisory_run_id: str
    parent_milestone: str
    worker_task_id: str
    worker_id: str
    role_id: str
    role_display_name: str
    workspace_id: str
    workspace_path: str
    approved_owner_branch: str
    approved_starting_sha: str
    expected_workspace_branch: str
    actual_starting_branch: str
    actual_ending_branch: str
    starting_head: str
    ending_head: str
    initial_workspace_status: str
    final_workspace_status: str
    initial_index_clean: bool
    final_index_clean: bool
    state_history: tuple[str, ...]
    effective_permissions: tuple[str, ...]
    requested_operations: tuple[WorkerOperation, ...]
    performed_operations: tuple[OperationResult, ...]
    denied_operations: tuple[OperationResult, ...]
    files_inspected: tuple[str, ...]
    files_changed: tuple[str, ...]
    untracked_files: tuple[str, ...]
    staged_files: tuple[str, ...]
    boundary_violations: tuple[str, ...]
    resource_violations: tuple[str, ...]
    contamination_findings: tuple[str, ...]
    validation_results: tuple[WorkerValidationResult, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]
    secret_redaction_result: str
    recommended_worker_state: str
    owner_review_required: bool
    action_audit: WorkerActionAudit
    started_at: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return _sanitize(asdict(self))


def write_worker_record(
    record: WorkerExecutionRecord, output_directory: Path
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / f"{record.execution_id}.json"
    markdown_path = output_directory / f"{record.execution_id}.md"
    payload = json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n"
    with json_path.open("x", encoding="utf-8") as stream:
        stream.write(payload)
    try:
        with markdown_path.open("x", encoding="utf-8") as stream:
            stream.write(render_worker_markdown(record))
    except BaseException:
        json_path.unlink(missing_ok=True)
        raise
    return json_path, markdown_path


def render_worker_markdown(record: WorkerExecutionRecord) -> str:
    def lines(values: tuple[str, ...]) -> list[str]:
        return [f"- {redact(value)}" for value in values] or ["- None."]

    return "\n".join(
        [
            "# LIA Worker Execution Record",
            "",
            f"- Execution: `{redact(record.execution_id)}`",
            f"- Supervisory run: `{redact(record.supervisory_run_id)}`",
            f"- Worker task: `{redact(record.worker_task_id)}`",
            f"- Worker: `{redact(record.worker_id)}` ({redact(record.role_display_name)})",
            f"- Workspace: `{redact(record.workspace_id)}`",
            f"- State: `{record.recommended_worker_state}`",
            f"- Owner review required: {record.owner_review_required}",
            "",
            "## Provenance",
            "",
            f"- Approved branch: `{redact(record.approved_owner_branch)}`",
            f"- Approved starting SHA: `{record.approved_starting_sha}`",
            f"- Workspace branch: `{redact(record.actual_ending_branch)}`",
            f"- Starting HEAD: `{record.starting_head}`",
            f"- Ending HEAD: `{record.ending_head}`",
            "",
            "## State history",
            "",
            *[f"- `{state}`" for state in record.state_history],
            "",
            "## Changed files",
            "",
            *lines(record.files_changed),
            "",
            "## Validation",
            "",
            *(
                [
                    f"- `{item.selection}`: {redact(item.result)} "
                    f"({item.exit_classification})"
                    for item in record.validation_results
                ]
                or ["- None."]
            ),
            "",
            "## Blockers and contamination",
            "",
            *lines(
                tuple(
                    (
                        *record.blockers,
                        *record.boundary_violations,
                        *record.resource_violations,
                        *record.contamination_findings,
                    )
                )
            ),
            "",
            "## Privileged-action audit",
            "",
            f"- Staged by factory: {record.action_audit.staged_by_factory}",
            f"- Committed by factory: {record.action_audit.committed_by_factory}",
            f"- Pushed by factory: {record.action_audit.pushed_by_factory}",
            f"- Merged by factory: {record.action_audit.merged_by_factory}",
            f"- Deployed by factory: {record.action_audit.deployed_by_factory}",
            "- Workspace deleted by factory: "
            f"{record.action_audit.workspace_deleted_by_factory}",
            "",
            "## Owner decision",
            "",
            "Validation and completion do not grant approval. Review this record and "
            "the unstaged workspace diff before any separately authorized action.",
            "",
        ]
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return WORKER_SECRET_PATTERN.sub(
            lambda match: f"{match.group(1)}[REDACTED]",
            redact(value),
        )
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value
