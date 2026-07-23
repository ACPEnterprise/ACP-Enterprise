from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from development_factory.execution_adapters import ExecutionAdapterError
from development_factory.worker_execution import (
    WorkerExecutionError,
    WorkerExecutor,
    WorkerState,
    transition_worker,
)
from development_factory.worker_records import render_worker_markdown
from development_factory.workspaces import WorkspaceManager


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="real worker lifecycle tests require the Git executable",
)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def contract_payload(
    head: str,
    *,
    code_changes: bool,
    branch: str = "main",
) -> dict[str, Any]:
    task_id = "DF4B-MUTATE" if code_changes else "DF4B-INSPECT"
    workspace_id = "df4b-mutate" if code_changes else "df4b-inspect"
    boundary = "docs/result.md" if code_changes else "docs/source.md"
    task = {
        "schema_version": "1.0",
        "task_id": task_id,
        "milestone": "DF.4B test",
        "objective": "Exercise one bounded worker.",
        "workflow_state": "approved",
        "approved_scope": ["Worker inspection", "Bounded demonstration mutation"],
        "prohibited_scope": ["Privileged actions", "Cleanup"],
        "expected_repository": {"branch": branch, "starting_head": head},
        "allowed_file_boundaries": [boundary],
        "required_validation": ["architecture"],
        "permissions": {
            "code_changes": code_changes,
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
        "required_report_fields": ["validation", "changed_files", "blockers"],
    }
    return {
        "schema_version": "1.0",
        "supervisory_run_id": f"DF4B-{'MUTATE' if code_changes else 'INSPECT'}",
        "parent_milestone": "DF.4B test",
        "objective": "Test bounded worker execution.",
        "workflow_state": "approved",
        "owner_approved_scope": [
            "Worker inspection",
            "Bounded demonstration mutation",
        ],
        "expected_repository": {"branch": branch, "starting_head": head},
        "parent_permissions": {
            "code_changes": code_changes,
            "stage_and_commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
        },
        "parallel_execution_approved": False,
        "workers": [
            {
                "agent_id": "atlas-worker",
                "role_id": "atlas",
                "task_contract": task,
                "depends_on": [],
                "exclusive_file_boundaries": [boundary],
                "shared_resources": [
                    {
                        "resource_type": "documentation",
                        "resource_id": "worker-result",
                        "mode": "exclusive",
                    }
                ],
                "parallel_eligible": False,
                "escalation_flags": [],
                "workspace": {
                    "strategy": "isolated_worktree",
                    "workspace_id": workspace_id,
                    "branch_hint": f"lia/{workspace_id}",
                },
            }
        ],
        "validation_requirements": ["architecture"],
        "integration_strategy": "owner_reviewed_sequence",
        "conflict_policy": "fail_closed",
        "stop_conditions": {
            "require_empty_index": True,
            "stop_on_repository_divergence": True,
            "stop_on_scope_expansion": True,
            "stop_on_conflict": True,
            "stop_on_validation_unavailable": True,
            "stop_on_privileged_action": True,
            "stop_on_destructive_action": True,
        },
        "required_report_fields": [
            "worker_assignments",
            "execution_waves",
            "owner_decisions",
        ],
        "owner_approval_requirements": {
            "architecture": True,
            "task_scope": True,
            "commit": True,
            "push": True,
            "merge": True,
            "deployment": True,
        },
    }


def operations_payload(*, code_changes: bool, execution_id: str) -> dict[str, Any]:
    task_id = "DF4B-MUTATE" if code_changes else "DF4B-INSPECT"
    workspace_id = "df4b-mutate" if code_changes else "df4b-inspect"
    operation: dict[str, Any] = {
        "operation_id": "bounded-operation",
        "operation": ("create_demonstration_file" if code_changes else "inspect_file"),
        "path": "docs/result.md" if code_changes else "docs/source.md",
        "paths": [],
        "text": "# bounded result\n" if code_changes else None,
        "expected_text": None,
        "replacement_text": None,
        "resource_type": "documentation",
        "resource_id": "worker-result",
    }
    return {
        "schema_version": "1.0",
        "execution_id": execution_id,
        "task_id": task_id,
        "workspace_id": workspace_id,
        "allowed_action_classes": (
            ["inspection", "mutation", "validation"]
            if code_changes
            else ["inspection", "validation"]
        ),
        "operations": [operation],
        "validation_selections": ["architecture"],
        "termination_policy": {
            "maximum_operations": 2,
            "maximum_mutations": 1,
            "maximum_files_inspected": 2,
            "maximum_files_changed": 1,
            "maximum_output_record_bytes": 1000000,
            "maximum_validation_selections": 1,
            "execution_timeout_seconds": 60,
        },
        "required_report_fields": [
            "state_history",
            "validation_results",
            "action_audit",
        ],
    }


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "factory@example.invalid")
    git(repo, "config", "user.name", "Development Factory")
    source_root = Path(__file__).parents[3]
    (repo / ".gitignore").write_text(".development-factory/\n", encoding="utf-8")
    factory = repo / "development-factory"
    factory.mkdir()
    for name in ("agent-roles.json", "config.json", "manifest.json"):
        shutil.copy(source_root / "development-factory" / name, factory / name)
    docs = repo / "docs"
    docs.mkdir()
    (docs / "source.md").write_text("# source\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    return repo, tmp_path


def prepare(
    repository: tuple[Path, Path], *, code_changes: bool
) -> tuple[WorkerExecutor, Path, Path, str]:
    repo, temp = repository
    head = git(repo, "rev-parse", "HEAD")
    contract = temp / f"{'mutation' if code_changes else 'inspection'}-contract.json"
    contract.write_text(
        json.dumps(contract_payload(head, code_changes=code_changes)),
        encoding="utf-8",
    )
    workspace_id = "df4b-mutate" if code_changes else "df4b-inspect"
    WorkspaceManager(repo).prepare(contract, workspace_id)
    operations = temp / f"{'mutation' if code_changes else 'inspection'}-ops.json"
    operations.write_text(
        json.dumps(
            operations_payload(
                code_changes=code_changes,
                execution_id=f"EXEC-{'MUTATE' if code_changes else 'INSPECT'}",
            )
        ),
        encoding="utf-8",
    )
    return WorkerExecutor(repo), contract, operations, head


def test_worker_state_transitions_fail_closed() -> None:
    assert (
        transition_worker(WorkerState.PENDING, WorkerState.WORKSPACE_VERIFYING)
        == WorkerState.WORKSPACE_VERIFYING
    )
    with pytest.raises(WorkerExecutionError, match="invalid worker transition"):
        transition_worker(WorkerState.PENDING, WorkerState.COMPLETED)


def test_inspection_worker_completes_without_mutation(
    repository: tuple[Path, Path],
) -> None:
    executor, contract, operations, head = prepare(repository, code_changes=False)
    record, json_path, markdown_path = executor.execute(
        contract, "DF4B-INSPECT", operations
    )
    assert record.recommended_worker_state == "completed"
    assert record.files_changed == ()
    assert record.files_inspected == ("docs/source.md",)
    assert record.ending_head == head
    assert record.action_audit.committed_by_factory is False
    assert json_path.exists() and markdown_path.exists()
    assert "Owner review required: True" in render_worker_markdown(record)
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "development-factory/worker-execution-record.schema.json"
        ).read_text()
    )
    assert set(record.to_dict()) == set(schema["required"])


def test_bounded_mutation_is_unstaged_uncommitted_and_primary_is_preserved(
    repository: tuple[Path, Path],
) -> None:
    repo, _ = repository
    executor, contract, operations, head = prepare(repository, code_changes=True)
    primary_branch = git(repo, "branch", "--show-current")
    record, _, _ = executor.execute(contract, "DF4B-MUTATE", operations)
    assert record.recommended_worker_state == "completed"
    assert record.files_changed == ("docs/result.md",)
    assert record.untracked_files == ("docs/result.md",)
    assert record.staged_files == ()
    assert record.starting_head == record.ending_head == head
    assert git(repo, "branch", "--show-current") == primary_branch
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain") == ""


def test_inspection_worker_mutation_and_out_of_boundary_are_denied(
    repository: tuple[Path, Path],
) -> None:
    executor, contract, operations, _ = prepare(repository, code_changes=False)
    payload = json.loads(operations.read_text(encoding="utf-8"))
    payload["allowed_action_classes"].append("mutation")
    payload["operations"][0]["operation"] = "write_text_file"
    payload["operations"][0]["text"] = "denied"
    operations.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WorkerExecutionError, match="effective permission"):
        executor.execute(contract, "DF4B-INSPECT", operations)

    mutation_executor, mutation_contract, mutation_operations, _ = prepare(
        repository, code_changes=True
    )
    payload = json.loads(mutation_operations.read_text(encoding="utf-8"))
    payload["execution_id"] = "EXEC-OUTSIDE"
    payload["operations"][0]["path"] = "outside.md"
    mutation_operations.write_text(json.dumps(payload), encoding="utf-8")
    record, _, _ = mutation_executor.execute(
        mutation_contract, "DF4B-MUTATE", mutation_operations
    )
    assert record.recommended_worker_state == "blocked"
    assert "outside approved file boundaries" in record.blockers[0]


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ("dirty_owner", "workspace verification failed"),
        ("dirty_workspace", "workspace verification failed"),
        ("staged_workspace", "workspace verification failed"),
        ("head_drift", "workspace verification failed"),
        ("missing_metadata", "workspace verification failed"),
    ],
)
def test_repository_and_workspace_contamination_blocks_execution(
    repository: tuple[Path, Path], condition: str, message: str
) -> None:
    repo, _ = repository
    executor, contract, operations, _ = prepare(repository, code_changes=True)
    manager = WorkspaceManager(repo)
    identity = manager.load(contract, "df4b-mutate")[2]
    workspace = Path(identity.workspace_path)
    if condition == "dirty_owner":
        (repo / "docs/source.md").write_text("dirty\n", encoding="utf-8")
    elif condition == "dirty_workspace":
        (workspace / "docs/source.md").write_text("dirty\n", encoding="utf-8")
    elif condition == "staged_workspace":
        (workspace / "docs/source.md").write_text("staged\n", encoding="utf-8")
        git(workspace, "add", "docs/source.md")
    elif condition == "head_drift":
        (workspace / "drift.txt").write_text("drift\n", encoding="utf-8")
        git(workspace, "add", "drift.txt")
        git(workspace, "commit", "-m", "unauthorized")
    else:
        manager._metadata_path(identity).unlink()
    with pytest.raises(WorkerExecutionError, match=message):
        executor.execute(contract, "DF4B-MUTATE", operations)


def test_permission_validation_resource_and_limit_fail_closed(
    repository: tuple[Path, Path],
) -> None:
    executor, contract, operations, _ = prepare(repository, code_changes=True)
    payload = json.loads(operations.read_text(encoding="utf-8"))
    payload["validation_selections"] = ["frontend"]
    operations.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WorkerExecutionError, match="parent selection"):
        executor.execute(contract, "DF4B-MUTATE", operations)

    payload = operations_payload(code_changes=True, execution_id="EXEC-RESOURCE")
    payload["operations"][0]["resource_id"] = "unknown"
    operations.write_text(json.dumps(payload), encoding="utf-8")
    record, _, _ = executor.execute(contract, "DF4B-MUTATE", operations)
    assert record.recommended_worker_state == "blocked"
    assert record.resource_violations

    payload = operations_payload(code_changes=True, execution_id="EXEC-LIMIT")
    payload["termination_policy"]["maximum_files_changed"] = 1
    second = copy.deepcopy(payload["operations"][0])
    second["operation_id"] = "second"
    second["path"] = "docs/second.md"
    payload["operations"].append(second)
    payload["termination_policy"]["maximum_operations"] = 1
    payload["termination_policy"]["maximum_mutations"] = 2
    operations.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ExecutionAdapterError, match="maximum"):
        executor.execute(contract, "DF4B-MUTATE", operations)


def test_record_is_immutable_and_cancellation_preserves_changes(
    repository: tuple[Path, Path],
) -> None:
    executor, contract, operations, _ = prepare(repository, code_changes=True)
    record, _, _ = executor.execute(contract, "DF4B-MUTATE", operations)
    with pytest.raises(WorkerExecutionError, match="finalized record state"):
        executor.execute(contract, "DF4B-MUTATE", operations)
    workspace = Path(record.workspace_path)
    before = (workspace / "docs/result.md").read_text()
    cancellation = executor.cancel(contract, "DF4B-MUTATE")
    assert json.loads(cancellation.read_text())["workspace_changes_preserved"] is True
    assert (workspace / "docs/result.md").read_text() == before


def test_partial_record_requires_owner_review(
    repository: tuple[Path, Path],
) -> None:
    executor, contract, operations, _ = prepare(repository, code_changes=True)
    partial = (
        repository[0]
        / ".development-factory"
        / "worker-executions"
        / "EXEC-MUTATE.json"
    )
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_text('{"partial": true}\n', encoding="utf-8")
    with pytest.raises(WorkerExecutionError, match="partial record state"):
        executor.execute(contract, "DF4B-MUTATE", operations)


def test_secret_like_content_is_redacted_and_blocks(
    repository: tuple[Path, Path],
) -> None:
    executor, contract, operations, _ = prepare(repository, code_changes=True)
    payload = json.loads(operations.read_text(encoding="utf-8"))
    payload["execution_id"] = "EXEC-SECRET"
    payload["operations"][0]["text"] = (
        "AWS_SECRET_ACCESS_KEY=not-a-real-secret-for-testing"
    )
    operations.write_text(json.dumps(payload), encoding="utf-8")
    record, json_path, markdown_path = executor.execute(
        contract, "DF4B-MUTATE", operations
    )
    assert record.recommended_worker_state == "blocked"
    assert "credential-like content detected" in record.contamination_findings[0]
    assert "not-a-real-secret-for-testing" not in json_path.read_text()
    assert "not-a-real-secret-for-testing" not in markdown_path.read_text()
