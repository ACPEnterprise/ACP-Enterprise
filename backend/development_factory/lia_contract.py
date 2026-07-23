from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from development_factory.lia_roles import AgentRole
from development_factory.task_contract import (
    TaskContract,
    TaskContractError,
    VALIDATION_AREAS,
    parse_task_contract,
)
from development_factory.workflow import ActionPermissions, WorkflowState


LIA_CONTRACT_VERSION = "1.0"
LIA_REPORT_FIELDS = frozenset(
    {
        "worker_assignments",
        "execution_waves",
        "dependency_status",
        "validation_summaries",
        "changed_file_boundaries",
        "conflicts",
        "blockers",
        "integration_recommendation",
        "owner_decisions",
        "privileged_action_confirmation",
    }
)
ResourceMode = Literal["exclusive", "shared"]
ResourceType = Literal[
    "migration",
    "shared_schema",
    "security_surface",
    "integration_surface",
    "database",
    "documentation",
]


class LiaContractError(ValueError):
    pass


@dataclass(frozen=True)
class ResourceClaim:
    resource_type: ResourceType
    resource_id: str
    mode: ResourceMode


@dataclass(frozen=True)
class IsolationWorkspace:
    strategy: Literal["isolated_worktree"]
    workspace_id: str
    branch_hint: str


@dataclass(frozen=True)
class WorkerAssignment:
    agent_id: str
    role_id: str
    task: TaskContract
    depends_on: tuple[str, ...]
    exclusive_file_boundaries: tuple[str, ...]
    shared_resources: tuple[ResourceClaim, ...]
    parallel_eligible: bool
    escalation_flags: tuple[str, ...]
    workspace: IsolationWorkspace


@dataclass(frozen=True)
class LiaStopConditions:
    require_empty_index: bool
    stop_on_repository_divergence: bool
    stop_on_scope_expansion: bool
    stop_on_conflict: bool
    stop_on_validation_unavailable: bool
    stop_on_privileged_action: bool
    stop_on_destructive_action: bool


@dataclass(frozen=True)
class OwnerApprovalRequirements:
    architecture: bool
    task_scope: bool
    commit: bool
    push: bool
    merge: bool
    deployment: bool


@dataclass(frozen=True)
class LiaSupervisoryContract:
    schema_version: str
    supervisory_run_id: str
    parent_milestone: str
    objective: str
    workflow_state: WorkflowState
    owner_approved_scope: tuple[str, ...]
    expected_branch: str
    expected_starting_head: str
    parent_permissions: ActionPermissions
    parallel_execution_approved: bool
    workers: tuple[WorkerAssignment, ...]
    validation_requirements: tuple[str, ...]
    integration_strategy: Literal["owner_reviewed_sequence"]
    conflict_policy: Literal["fail_closed"]
    stop_conditions: LiaStopConditions
    required_report_fields: tuple[str, ...]
    owner_approval_requirements: OwnerApprovalRequirements


def load_lia_contract(
    path: Path, roles: dict[str, AgentRole]
) -> LiaSupervisoryContract:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiaContractError(f"unable to load LIA contract: {exc}") from exc
    return parse_lia_contract(payload, roles)


def parse_lia_contract(
    payload: object, roles: dict[str, AgentRole]
) -> LiaSupervisoryContract:
    if not isinstance(payload, dict):
        raise LiaContractError("LIA supervisory contract must be an object")
    expected = {
        "schema_version",
        "supervisory_run_id",
        "parent_milestone",
        "objective",
        "workflow_state",
        "owner_approved_scope",
        "expected_repository",
        "parent_permissions",
        "parallel_execution_approved",
        "workers",
        "validation_requirements",
        "integration_strategy",
        "conflict_policy",
        "stop_conditions",
        "required_report_fields",
        "owner_approval_requirements",
    }
    _exact_keys(payload, expected, "LIA supervisory contract")
    if payload["schema_version"] != LIA_CONTRACT_VERSION:
        raise LiaContractError(
            f"LIA contract schema_version must be {LIA_CONTRACT_VERSION}"
        )
    run_id = _nonblank(payload["supervisory_run_id"], "supervisory_run_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", run_id):
        raise LiaContractError("supervisory_run_id has an invalid format")
    repository = _object(payload["expected_repository"], "expected_repository")
    _exact_keys(repository, {"branch", "starting_head"}, "expected_repository")
    head = _nonblank(repository["starting_head"], "starting_head")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise LiaContractError("starting_head must be a full lowercase SHA")
    scope = _strings(payload["owner_approved_scope"], "owner_approved_scope")
    permissions = _permissions(payload["parent_permissions"])
    if not isinstance(payload["parallel_execution_approved"], bool):
        raise LiaContractError("parallel_execution_approved must be boolean")
    raw_workers = payload["workers"]
    if not isinstance(raw_workers, list) or not raw_workers:
        raise LiaContractError("workers must be a non-empty array")
    workers = tuple(_worker(item, roles) for item in raw_workers)
    worker_ids = [item.agent_id for item in workers]
    task_ids = [item.task.task_id for item in workers]
    if len(worker_ids) != len(set(worker_ids)):
        raise LiaContractError("duplicate worker agent_id")
    if len(task_ids) != len(set(task_ids)):
        raise LiaContractError("duplicate worker task_id")
    try:
        state = WorkflowState(str(payload["workflow_state"]))
    except ValueError as exc:
        raise LiaContractError("workflow_state is invalid") from exc
    if state != WorkflowState.APPROVED:
        raise LiaContractError("LIA dry-run contract must be owner-approved")
    approvals = _approvals(payload["owner_approval_requirements"])
    if not all(approvals.__dict__.values()):
        raise LiaContractError("all privileged decisions must remain owner-approved")
    stop_conditions = _stop_conditions(payload["stop_conditions"])
    validation = _strings(payload["validation_requirements"], "validation_requirements")
    if not set(validation) <= VALIDATION_AREAS:
        raise LiaContractError("validation_requirements contains an unsupported area")
    if any(item in validation for item in ("all", "changed")) and len(validation) != 1:
        raise LiaContractError(
            "all or changed cannot be combined with other validation requirements"
        )
    report_fields = _strings(
        payload["required_report_fields"], "required_report_fields"
    )
    unknown_report_fields = set(report_fields) - LIA_REPORT_FIELDS
    if unknown_report_fields:
        raise LiaContractError(
            "required_report_fields contains unsupported fields: "
            + ", ".join(sorted(unknown_report_fields))
        )
    contract = LiaSupervisoryContract(
        schema_version=LIA_CONTRACT_VERSION,
        supervisory_run_id=run_id,
        parent_milestone=_nonblank(payload["parent_milestone"], "parent_milestone"),
        objective=_nonblank(payload["objective"], "objective"),
        workflow_state=state,
        owner_approved_scope=scope,
        expected_branch=_nonblank(repository["branch"], "branch"),
        expected_starting_head=head,
        parent_permissions=permissions,
        parallel_execution_approved=payload["parallel_execution_approved"],
        workers=workers,
        validation_requirements=validation,
        integration_strategy=_literal(
            payload["integration_strategy"],
            "integration_strategy",
            {"owner_reviewed_sequence"},
        ),
        conflict_policy=_literal(
            payload["conflict_policy"], "conflict_policy", {"fail_closed"}
        ),
        stop_conditions=stop_conditions,
        required_report_fields=report_fields,
        owner_approval_requirements=approvals,
    )
    _validate_inheritance(contract, roles)
    from development_factory.lia_planner import validate_decomposition

    validate_decomposition(contract)
    return contract


def _worker(value: object, roles: dict[str, AgentRole]) -> WorkerAssignment:
    payload = _object(value, "worker")
    expected = {
        "agent_id",
        "role_id",
        "task_contract",
        "depends_on",
        "exclusive_file_boundaries",
        "shared_resources",
        "parallel_eligible",
        "escalation_flags",
        "workspace",
    }
    _exact_keys(payload, expected, "worker")
    role_id = _nonblank(payload["role_id"], "role_id")
    if role_id not in roles:
        raise LiaContractError(f"unknown agent role: {role_id}")
    try:
        task = parse_task_contract(payload["task_contract"])
    except TaskContractError as exc:
        raise LiaContractError(f"invalid worker task contract: {exc}") from exc
    if not isinstance(payload["parallel_eligible"], bool):
        raise LiaContractError("parallel_eligible must be boolean")
    resources_value = payload["shared_resources"]
    if not isinstance(resources_value, list):
        raise LiaContractError("shared_resources must be an array")
    workspace = _object(payload["workspace"], "workspace")
    _exact_keys(workspace, {"strategy", "workspace_id", "branch_hint"}, "workspace")
    if workspace["strategy"] != "isolated_worktree":
        raise LiaContractError("workspace strategy must be isolated_worktree")
    return WorkerAssignment(
        agent_id=_nonblank(payload["agent_id"], "agent_id"),
        role_id=role_id,
        task=task,
        depends_on=_strings(payload["depends_on"], "depends_on", allow_empty=True),
        exclusive_file_boundaries=_strings(
            payload["exclusive_file_boundaries"],
            "exclusive_file_boundaries",
            allow_empty=True,
        ),
        shared_resources=tuple(_resource(item) for item in resources_value),
        parallel_eligible=payload["parallel_eligible"],
        escalation_flags=_strings(
            payload["escalation_flags"], "escalation_flags", allow_empty=True
        ),
        workspace=IsolationWorkspace(
            strategy="isolated_worktree",
            workspace_id=_nonblank(workspace["workspace_id"], "workspace_id"),
            branch_hint=_nonblank(workspace["branch_hint"], "branch_hint"),
        ),
    )


def _resource(value: object) -> ResourceClaim:
    payload = _object(value, "resource claim")
    _exact_keys(payload, {"resource_type", "resource_id", "mode"}, "resource claim")
    resource_type = _literal(
        payload["resource_type"],
        "resource_type",
        {
            "migration",
            "shared_schema",
            "security_surface",
            "integration_surface",
            "database",
            "documentation",
        },
    )
    mode = _literal(payload["mode"], "mode", {"exclusive", "shared"})
    return ResourceClaim(
        resource_type=resource_type,
        resource_id=_nonblank(payload["resource_id"], "resource_id"),
        mode=mode,
    )


def _validate_inheritance(
    contract: LiaSupervisoryContract, roles: dict[str, AgentRole]
) -> None:
    approved = set(contract.owner_approved_scope)
    parent = contract.parent_permissions
    for worker in contract.workers:
        if worker.task.expected_branch != contract.expected_branch:
            raise LiaContractError(f"worker {worker.agent_id} branch mismatch")
        if worker.task.expected_starting_head != contract.expected_starting_head:
            raise LiaContractError(f"worker {worker.agent_id} starting HEAD mismatch")
        if not set(worker.task.approved_scope) <= approved:
            raise LiaContractError(
                f"worker {worker.agent_id} scope exceeds parent scope"
            )
        child = worker.task.permissions
        for name in (
            "code_changes",
            "stage_and_commit",
            "push",
            "merge",
            "deployment",
        ):
            if getattr(child, name) and not getattr(parent, name):
                raise LiaContractError(
                    f"worker {worker.agent_id} permission {name} exceeds parent"
                )
        role = roles[worker.role_id]
        if child.code_changes and not role.may_propose_code_changes:
            raise LiaContractError(
                f"worker {worker.agent_id} role cannot propose code changes"
            )
        if any(
            (
                child.stage_and_commit,
                child.push,
                child.merge,
                child.deployment,
                role.may_commit,
                role.may_push,
                role.may_merge,
                role.may_deploy,
            )
        ):
            raise LiaContractError(
                f"worker {worker.agent_id} cannot receive privileged authority"
            )


def _permissions(value: object) -> ActionPermissions:
    payload = _object(value, "parent_permissions")
    expected = {
        "code_changes",
        "stage_and_commit",
        "push",
        "merge",
        "deployment",
    }
    _exact_keys(payload, expected, "parent_permissions")
    if not all(isinstance(payload[key], bool) for key in expected):
        raise LiaContractError("parent permissions must be booleans")
    return ActionPermissions(**{key: payload[key] for key in expected})


def _approvals(value: object) -> OwnerApprovalRequirements:
    payload = _object(value, "owner_approval_requirements")
    expected = {"architecture", "task_scope", "commit", "push", "merge", "deployment"}
    _exact_keys(payload, expected, "owner_approval_requirements")
    if not all(isinstance(payload[key], bool) for key in expected):
        raise LiaContractError("owner approval requirements must be booleans")
    return OwnerApprovalRequirements(**{key: payload[key] for key in expected})


def _stop_conditions(value: object) -> LiaStopConditions:
    payload = _object(value, "stop_conditions")
    expected = {
        "require_empty_index",
        "stop_on_repository_divergence",
        "stop_on_scope_expansion",
        "stop_on_conflict",
        "stop_on_validation_unavailable",
        "stop_on_privileged_action",
        "stop_on_destructive_action",
    }
    _exact_keys(payload, expected, "stop_conditions")
    if not all(isinstance(payload[key], bool) for key in expected):
        raise LiaContractError("LIA stop conditions must be booleans")
    if not all(payload.values()):
        raise LiaContractError("all LIA stop conditions must fail closed")
    return LiaStopConditions(**{key: payload[key] for key in expected})


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LiaContractError(f"{field} must be an object")
    return value


def _strings(
    value: object, field: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise LiaContractError(f"{field} must be a string array")
    result = tuple(item.strip() for item in value)
    if len(result) != len(set(result)):
        raise LiaContractError(f"{field} cannot contain duplicates")
    return result


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiaContractError(f"{field} must be nonblank")
    return value.strip()


def _literal(value: object, field: str, allowed: set[str]) -> Any:
    if not isinstance(value, str) or value not in allowed:
        raise LiaContractError(f"{field} is invalid")
    return value


def _exact_keys(payload: dict[str, Any], expected: set[str], field: str) -> None:
    if payload.keys() != expected:
        raise LiaContractError(f"{field} fields are invalid")
