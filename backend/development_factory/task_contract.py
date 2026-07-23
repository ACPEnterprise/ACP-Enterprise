from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from development_factory.workflow import ActionPermissions, WorkflowState


TASK_CONTRACT_VERSION = "1.0"
TASK_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,63}$", re.IGNORECASE)
VALIDATION_AREAS = frozenset(
    {"all", "backend", "frontend", "migrations", "architecture", "changed"}
)
REPORT_FIELDS = frozenset(
    {
        "starting_state",
        "repository_inspection",
        "architecture",
        "security",
        "validation",
        "changed_files",
        "blockers",
        "next_action",
        "git_status",
        "prohibited_action_confirmation",
    }
)


class TaskContractError(ValueError):
    pass


@dataclass(frozen=True)
class StopConditions:
    require_clean_start: bool
    require_empty_index: bool
    stop_on_branch_mismatch: bool
    stop_on_head_mismatch: bool
    stop_on_unapproved_files: bool


@dataclass(frozen=True)
class TaskContract:
    schema_version: str
    task_id: str
    milestone: str
    objective: str
    workflow_state: WorkflowState
    approved_scope: tuple[str, ...]
    prohibited_scope: tuple[str, ...]
    expected_branch: str
    expected_starting_head: str
    allowed_file_boundaries: tuple[str, ...]
    required_validation: tuple[str, ...]
    permissions: ActionPermissions
    stop_conditions: StopConditions
    required_report_fields: tuple[str, ...]


def load_task_contract(path: Path) -> TaskContract:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskContractError(f"unable to load task contract: {exc}") from exc
    if not isinstance(payload, dict):
        raise TaskContractError("task contract must be an object")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "task_id",
            "milestone",
            "objective",
            "workflow_state",
            "approved_scope",
            "prohibited_scope",
            "expected_repository",
            "allowed_file_boundaries",
            "required_validation",
            "permissions",
            "stop_conditions",
            "required_report_fields",
        },
        "task contract",
    )
    if payload["schema_version"] != TASK_CONTRACT_VERSION:
        raise TaskContractError(
            f"task contract schema_version must be {TASK_CONTRACT_VERSION}"
        )
    task_id = _nonblank(payload["task_id"], "task_id")
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise TaskContractError("task_id has an invalid format")
    approved_scope = _string_tuple(payload["approved_scope"], "approved_scope")
    prohibited_scope = _string_tuple(payload["prohibited_scope"], "prohibited_scope")
    if not approved_scope or not prohibited_scope:
        raise TaskContractError("approved_scope and prohibited_scope cannot be empty")

    repository = _object(payload["expected_repository"], "expected_repository")
    _require_exact_keys(repository, {"branch", "starting_head"}, "expected_repository")
    branch = _nonblank(repository["branch"], "expected_repository.branch")
    head = _nonblank(repository["starting_head"], "expected_repository.starting_head")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise TaskContractError("expected starting HEAD must be a full lowercase SHA")

    validation = _string_tuple(payload["required_validation"], "required_validation")
    if not validation or not set(validation) <= VALIDATION_AREAS:
        raise TaskContractError("required_validation contains an unsupported area")
    if "all" in validation and len(validation) != 1:
        raise TaskContractError("'all' cannot be combined with validation areas")
    if "changed" in validation and len(validation) != 1:
        raise TaskContractError("'changed' cannot be combined with validation areas")

    permissions = _parse_permissions(payload["permissions"])
    stop_conditions = _parse_stop_conditions(payload["stop_conditions"])
    report_fields = _string_tuple(
        payload["required_report_fields"], "required_report_fields"
    )
    unknown_fields = set(report_fields) - REPORT_FIELDS
    if unknown_fields:
        raise TaskContractError(
            f"unsupported required report fields: {', '.join(sorted(unknown_fields))}"
        )

    try:
        state = WorkflowState(str(payload["workflow_state"]))
    except ValueError as exc:
        raise TaskContractError("workflow_state is invalid") from exc
    return TaskContract(
        schema_version=TASK_CONTRACT_VERSION,
        task_id=task_id,
        milestone=_nonblank(payload["milestone"], "milestone"),
        objective=_nonblank(payload["objective"], "objective"),
        workflow_state=state,
        approved_scope=approved_scope,
        prohibited_scope=prohibited_scope,
        expected_branch=branch,
        expected_starting_head=head,
        allowed_file_boundaries=_string_tuple(
            payload["allowed_file_boundaries"], "allowed_file_boundaries"
        ),
        required_validation=validation,
        permissions=permissions,
        stop_conditions=stop_conditions,
        required_report_fields=report_fields,
    )


def _parse_permissions(value: object) -> ActionPermissions:
    payload = _object(value, "permissions")
    keys = {
        "code_changes",
        "stage_and_commit",
        "push",
        "merge",
        "deployment",
    }
    _require_exact_keys(payload, keys, "permissions")
    if not all(isinstance(payload[key], bool) for key in keys):
        raise TaskContractError("all permission values must be booleans")
    return ActionPermissions(
        code_changes=payload["code_changes"],
        stage_and_commit=payload["stage_and_commit"],
        push=payload["push"],
        merge=payload["merge"],
        deployment=payload["deployment"],
    )


def _parse_stop_conditions(value: object) -> StopConditions:
    payload = _object(value, "stop_conditions")
    keys = {
        "require_clean_start",
        "require_empty_index",
        "stop_on_branch_mismatch",
        "stop_on_head_mismatch",
        "stop_on_unapproved_files",
    }
    _require_exact_keys(payload, keys, "stop_conditions")
    if not all(isinstance(payload[key], bool) for key in keys):
        raise TaskContractError("all stop-condition values must be booleans")
    return StopConditions(**{key: payload[key] for key in keys})


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TaskContractError(f"{field} must be an object")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise TaskContractError(f"{field} must be an array of nonblank strings")
    values = tuple(item.strip() for item in value)
    if len(values) != len(set(values)):
        raise TaskContractError(f"{field} cannot contain duplicates")
    return values


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskContractError(f"{field} must be a nonblank string")
    return value.strip()


def _require_exact_keys(
    payload: dict[str, Any], expected: set[str], field: str
) -> None:
    missing = expected - payload.keys()
    extra = payload.keys() - expected
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unexpected {', '.join(sorted(extra))}")
        raise TaskContractError(f"{field} fields invalid: {'; '.join(details)}")
