from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from development_factory.automation import TaskRunner
from development_factory.run_records import (
    RUN_RECORD_VERSION,
    RunActionAudit,
    RunRecord,
    render_run_markdown,
    write_run_record,
)
from development_factory.task_contract import (
    TASK_CONTRACT_VERSION,
    TaskContractError,
    load_task_contract,
)
from development_factory.workflow import (
    Action,
    ActionPermissions,
    WorkflowError,
    WorkflowState,
    ensure_action_allowed,
    transition,
)


def contract_payload(head: str = "a" * 40, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": TASK_CONTRACT_VERSION,
        "task_id": "DF2-TEST",
        "milestone": "DF.2",
        "objective": "Validate task automation.",
        "workflow_state": "approved",
        "approved_scope": ["inspection", "validation"],
        "prohibited_scope": ["remote mutation"],
        "expected_repository": {
            "branch": "customer-management-v1",
            "starting_head": head,
        },
        "allowed_file_boundaries": ["backend/development_factory/*.py"],
        "required_validation": ["all"],
        "permissions": {
            "code_changes": True,
            "stage_and_commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
        },
        "stop_conditions": {
            "require_clean_start": True,
            "require_empty_index": True,
            "stop_on_branch_mismatch": True,
            "stop_on_head_mismatch": True,
            "stop_on_unapproved_files": True,
        },
        "required_report_fields": [
            "starting_state",
            "validation",
            "changed_files",
            "blockers",
        ],
    }
    payload.update(overrides)
    return payload


def write_contract(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_task_contract_is_strict_validated_and_immutable(tmp_path: Path) -> None:
    path = tmp_path / "task.json"
    write_contract(path, contract_payload())
    contract = load_task_contract(path)
    assert contract.task_id == "DF2-TEST"
    assert contract.required_validation == ("all",)
    assert not contract.permissions.stage_and_commit
    with pytest.raises(FrozenInstanceError):
        contract.objective = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    [
        contract_payload(schema_version="2.0"),
        contract_payload(task_id="x"),
        contract_payload(required_validation=["all", "backend"]),
        contract_payload(required_validation=["unknown"]),
        contract_payload(unexpected=True),
        contract_payload(
            expected_repository={
                "branch": "customer-management-v1",
                "starting_head": "short",
            }
        ),
        contract_payload(workflow_state="unknown"),
    ],
)
def test_invalid_task_contracts_fail_closed(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    path = tmp_path / "task.json"
    write_contract(path, payload)
    with pytest.raises(TaskContractError):
        load_task_contract(path)


def test_workflow_transitions_require_explicit_approval_states() -> None:
    allowed = ActionPermissions(stage_and_commit=True)
    assert (
        transition(WorkflowState.PROPOSED, WorkflowState.APPROVED, allowed)
        == WorkflowState.APPROVED
    )
    with pytest.raises(WorkflowError, match="invalid workflow transition"):
        transition(WorkflowState.APPROVED, WorkflowState.COMMITTED, allowed)
    with pytest.raises(WorkflowError, match="not permitted"):
        transition(
            WorkflowState.READY_FOR_OWNER_REVIEW,
            WorkflowState.APPROVED_FOR_COMMIT,
            ActionPermissions(),
        )
    approved = transition(
        WorkflowState.READY_FOR_OWNER_REVIEW,
        WorkflowState.APPROVED_FOR_COMMIT,
        allowed,
    )
    assert (
        transition(approved, WorkflowState.COMMITTED, allowed)
        == WorkflowState.COMMITTED
    )


@pytest.mark.parametrize(
    ("action", "state"),
    [
        (Action.STAGE_AND_COMMIT, WorkflowState.READY_FOR_OWNER_REVIEW),
        (Action.PUSH, WorkflowState.COMMITTED),
        (Action.MERGE, WorkflowState.PUSHED),
        (Action.DEPLOYMENT, WorkflowState.MERGED),
        (Action.DESTRUCTIVE, WorkflowState.APPROVED),
    ],
)
def test_unauthorized_or_unapproved_actions_fail_closed(
    action: Action, state: WorkflowState
) -> None:
    with pytest.raises(WorkflowError):
        ensure_action_allowed(action, state, ActionPermissions())


def test_action_needs_permission_and_matching_approval_state() -> None:
    permissions = ActionPermissions(push=True)
    with pytest.raises(WorkflowError, match="requires workflow state"):
        ensure_action_allowed(Action.PUSH, WorkflowState.COMMITTED, permissions)
    ensure_action_allowed(Action.PUSH, WorkflowState.APPROVED_FOR_PUSH, permissions)


def test_run_record_is_versioned_redacted_and_human_readable(tmp_path: Path) -> None:
    record = RunRecord(
        schema_version=RUN_RECORD_VERSION,
        run_id="df2-test-20260723",
        task_id="DF2-TEST",
        milestone="DF.2",
        started_at="2026-07-23T12:00:00+00:00",
        completed_at="2026-07-23T12:01:00+00:00",
        starting_branch="customer-management-v1",
        starting_head="a" * 40,
        ending_branch="customer-management-v1",
        ending_head="a" * 40,
        working_tree_clean_at_start=True,
        working_tree_clean_at_end=True,
        index_clean_at_start=True,
        index_clean_at_end=True,
        commands_executed=("repository.inspect",),
        validation_result="token=do-not-record",
        changed_files=(),
        workflow_state=WorkflowState.APPROVED,
        blockers=(),
        recommended_next_action="Owner review.",
        actions=RunActionAudit(),
        dry_run=True,
    )
    json_path, markdown_path = write_run_record(record, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == RUN_RECORD_VERSION
    assert payload["validation_result"] == "token=[REDACTED]"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# ACP Development Factory Task Run" in markdown
    assert "Commit occurred: False" in markdown
    assert "do-not-record" not in render_run_markdown(record)


def test_dry_run_generates_record_without_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from development_factory.models import RepositoryState

    head = "a" * 40
    state = RepositoryState(branch="customer-management-v1", head=head)
    monkeypatch.setattr(
        "development_factory.automation.inspect_repository", lambda _root: state
    )
    contract_path = tmp_path / "task.json"
    payload = contract_payload(
        head=head,
        stop_conditions={
            "require_clean_start": False,
            "require_empty_index": True,
            "stop_on_branch_mismatch": True,
            "stop_on_head_mismatch": True,
            "stop_on_unapproved_files": False,
        },
    )
    write_contract(contract_path, payload)
    runner = TaskRunner(tmp_path)
    record, json_path, markdown_path = runner.run(contract_path, dry_run=True)
    assert record.workflow_state == WorkflowState.APPROVED
    assert record.commands_executed == ("repository.inspect",)
    assert record.actions == RunActionAudit()
    assert json_path.exists() and markdown_path.exists()


def test_repository_mismatch_and_unapproved_file_are_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "task.json"
    write_contract(path, contract_payload())
    runner = TaskRunner(tmp_path)
    from development_factory.models import ClassifiedFile, RepositoryState

    state = RepositoryState(
        branch="wrong",
        head="b" * 40,
        files=[
            ClassifiedFile(
                "frontend/src/unapproved.ts", " M", "frontend_runtime", False, False
            )
        ],
    )
    monkeypatch.setattr(
        "development_factory.automation.inspect_repository", lambda _root: state
    )
    contract, issues = runner.inspect(path)
    assert contract.task_id == "DF2-TEST"
    assert any("branch mismatch" in issue for issue in issues)
    assert any("HEAD mismatch" in issue for issue in issues)
    assert any("working tree must be clean" in issue for issue in issues)
    assert runner._boundary_issues(contract, state) == (
        "unapproved changed file: frontend/src/unapproved.ts",
    )
