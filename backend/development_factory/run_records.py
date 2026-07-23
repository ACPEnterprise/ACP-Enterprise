from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from development_factory.models import RepositoryState
from development_factory.reports import redact
from development_factory.workflow import WorkflowState


RUN_RECORD_VERSION = "1.0"


@dataclass(frozen=True)
class RunActionAudit:
    committed: bool = False
    pushed: bool = False
    merged: bool = False
    deployed: bool = False


@dataclass(frozen=True)
class RunRecord:
    schema_version: str
    run_id: str
    task_id: str
    milestone: str
    started_at: str
    completed_at: str
    starting_branch: str
    starting_head: str
    ending_branch: str
    ending_head: str
    working_tree_clean_at_start: bool
    working_tree_clean_at_end: bool
    index_clean_at_start: bool
    index_clean_at_end: bool
    commands_executed: tuple[str, ...]
    validation_result: str
    changed_files: tuple[str, ...]
    workflow_state: WorkflowState
    blockers: tuple[str, ...]
    recommended_next_action: str
    actions: RunActionAudit
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workflow_state"] = self.workflow_state.value
        return _sanitize(payload)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id(task_id: str, started_at: str) -> str:
    compact = "".join(character for character in started_at if character.isdigit())[:20]
    return f"{task_id.lower()}-{compact}"


def write_run_record(record: RunRecord, output_directory: Path) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / f"{record.run_id}.json"
    markdown_path = output_directory / f"{record.run_id}.md"
    json_path.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_run_markdown(record), encoding="utf-8")
    return json_path, markdown_path


def render_run_markdown(record: RunRecord) -> str:
    blockers = (
        "\n".join(f"- {redact(item)}" for item in record.blockers)
        if record.blockers
        else "- None."
    )
    changed = (
        "\n".join(f"- `{item}`" for item in record.changed_files)
        if record.changed_files
        else "- None."
    )
    return "\n".join(
        [
            "# ACP Development Factory Task Run",
            "",
            f"- Task: `{record.task_id}`",
            f"- Milestone: {redact(record.milestone)}",
            f"- State: `{record.workflow_state.value}`",
            f"- Dry run: {record.dry_run}",
            f"- Starting HEAD: `{record.starting_head}`",
            f"- Ending HEAD: `{record.ending_head}`",
            "",
            "## Validation",
            "",
            f"- Result: {redact(record.validation_result)}",
            *[f"- Executed: `{item}`" for item in record.commands_executed],
            "",
            "## Changed files",
            "",
            changed,
            "",
            "## Blockers",
            "",
            blockers,
            "",
            "## Action audit",
            "",
            f"- Commit occurred: {record.actions.committed}",
            f"- Push occurred: {record.actions.pushed}",
            f"- Merge occurred: {record.actions.merged}",
            f"- Deployment occurred: {record.actions.deployed}",
            "",
            "## Recommended next action",
            "",
            redact(record.recommended_next_action),
            "",
        ]
    )


def state_snapshot(state: RepositoryState) -> tuple[str, ...]:
    return tuple(sorted(item.path for item in state.files))


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value
