from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowError(ValueError):
    pass


class WorkflowState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    BLOCKED = "blocked"
    READY_FOR_OWNER_REVIEW = "ready_for_owner_review"
    APPROVED_FOR_COMMIT = "approved_for_commit"
    COMMITTED = "committed"
    APPROVED_FOR_PUSH = "approved_for_push"
    PUSHED = "pushed"
    APPROVED_FOR_MERGE = "approved_for_merge"
    MERGED = "merged"
    APPROVED_FOR_DEPLOYMENT = "approved_for_deployment"
    DEPLOYED = "deployed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Action(str, Enum):
    INSPECTION = "inspection"
    VALIDATION = "validation"
    CODE_CHANGE = "code_change"
    STAGE_AND_COMMIT = "stage_and_commit"
    PUSH = "push"
    MERGE = "merge"
    DEPLOYMENT = "deployment"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ActionPermissions:
    code_changes: bool = False
    stage_and_commit: bool = False
    push: bool = False
    merge: bool = False
    deployment: bool = False


TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.PROPOSED: frozenset(
        {WorkflowState.APPROVED, WorkflowState.REJECTED, WorkflowState.CANCELLED}
    ),
    WorkflowState.APPROVED: frozenset(
        {WorkflowState.RUNNING, WorkflowState.REJECTED, WorkflowState.CANCELLED}
    ),
    WorkflowState.RUNNING: frozenset(
        {
            WorkflowState.BLOCKED,
            WorkflowState.READY_FOR_OWNER_REVIEW,
            WorkflowState.CANCELLED,
        }
    ),
    WorkflowState.BLOCKED: frozenset(
        {WorkflowState.APPROVED, WorkflowState.REJECTED, WorkflowState.CANCELLED}
    ),
    WorkflowState.READY_FOR_OWNER_REVIEW: frozenset(
        {
            WorkflowState.APPROVED_FOR_COMMIT,
            WorkflowState.REJECTED,
            WorkflowState.CANCELLED,
        }
    ),
    WorkflowState.APPROVED_FOR_COMMIT: frozenset(
        {WorkflowState.COMMITTED, WorkflowState.CANCELLED}
    ),
    WorkflowState.COMMITTED: frozenset(
        {WorkflowState.APPROVED_FOR_PUSH, WorkflowState.CANCELLED}
    ),
    WorkflowState.APPROVED_FOR_PUSH: frozenset(
        {WorkflowState.PUSHED, WorkflowState.CANCELLED}
    ),
    WorkflowState.PUSHED: frozenset(
        {WorkflowState.APPROVED_FOR_MERGE, WorkflowState.CANCELLED}
    ),
    WorkflowState.APPROVED_FOR_MERGE: frozenset(
        {WorkflowState.MERGED, WorkflowState.CANCELLED}
    ),
    WorkflowState.MERGED: frozenset(
        {WorkflowState.APPROVED_FOR_DEPLOYMENT, WorkflowState.CANCELLED}
    ),
    WorkflowState.APPROVED_FOR_DEPLOYMENT: frozenset(
        {WorkflowState.DEPLOYED, WorkflowState.CANCELLED}
    ),
    WorkflowState.DEPLOYED: frozenset(),
    WorkflowState.REJECTED: frozenset(),
    WorkflowState.CANCELLED: frozenset(),
}


def transition(
    current: WorkflowState,
    target: WorkflowState,
    permissions: ActionPermissions,
) -> WorkflowState:
    if target not in TRANSITIONS[current]:
        raise WorkflowError(
            f"invalid workflow transition: {current.value} -> {target.value}"
        )
    approval_permission = {
        WorkflowState.APPROVED_FOR_COMMIT: permissions.stage_and_commit,
        WorkflowState.APPROVED_FOR_PUSH: permissions.push,
        WorkflowState.APPROVED_FOR_MERGE: permissions.merge,
        WorkflowState.APPROVED_FOR_DEPLOYMENT: permissions.deployment,
    }.get(target)
    if approval_permission is False:
        raise WorkflowError(f"{target.value} is not permitted by the task contract")
    action = {
        WorkflowState.COMMITTED: Action.STAGE_AND_COMMIT,
        WorkflowState.PUSHED: Action.PUSH,
        WorkflowState.MERGED: Action.MERGE,
        WorkflowState.DEPLOYED: Action.DEPLOYMENT,
    }.get(target)
    if action is not None:
        ensure_action_allowed(action, current, permissions)
    return target


def ensure_action_allowed(
    action: Action,
    state: WorkflowState,
    permissions: ActionPermissions,
) -> None:
    if action in {Action.INSPECTION, Action.VALIDATION}:
        return
    if action == Action.DESTRUCTIVE:
        raise WorkflowError("destructive actions are not executable by DF.2")
    requirements = {
        Action.CODE_CHANGE: (permissions.code_changes, WorkflowState.RUNNING),
        Action.STAGE_AND_COMMIT: (
            permissions.stage_and_commit,
            WorkflowState.APPROVED_FOR_COMMIT,
        ),
        Action.PUSH: (permissions.push, WorkflowState.APPROVED_FOR_PUSH),
        Action.MERGE: (permissions.merge, WorkflowState.APPROVED_FOR_MERGE),
        Action.DEPLOYMENT: (
            permissions.deployment,
            WorkflowState.APPROVED_FOR_DEPLOYMENT,
        ),
    }
    permitted, required_state = requirements[action]
    if not permitted:
        raise WorkflowError(f"{action.value} is not permitted by the task contract")
    if state != required_state:
        raise WorkflowError(
            f"{action.value} requires workflow state {required_state.value}"
        )
