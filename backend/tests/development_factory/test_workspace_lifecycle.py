from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from development_factory.workspaces import WorkspaceError, WorkspaceManager


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="real workspace lifecycle tests require the Git executable",
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


def roles_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "roles": [
            {
                "role_id": "atlas",
                "display_name": "Atlas",
                "responsibilities": ["Backend architecture"],
                "prohibited_responsibilities": ["Privileged actions"],
                "default_validation": ["architecture"],
                "escalation_conditions": ["Boundary is unclear"],
                "may_propose_code_changes": True,
                "may_review_other_work": True,
                "privileged_authority": {
                    "commit": False,
                    "push": False,
                    "merge": False,
                    "deployment": False,
                },
            }
        ],
    }


def contract_payload(head: str, branch: str = "main") -> dict[str, Any]:
    task = {
        "schema_version": "1.0",
        "task_id": "DF4A-WORKER",
        "milestone": "DF.4A test",
        "objective": "Prepare one isolated workspace.",
        "workflow_state": "approved",
        "approved_scope": ["Workspace preparation"],
        "prohibited_scope": ["Worker execution", "Privileged actions"],
        "expected_repository": {"branch": branch, "starting_head": head},
        "allowed_file_boundaries": ["docs/worker.md"],
        "required_validation": ["architecture"],
        "permissions": {
            "code_changes": False,
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
        "required_report_fields": ["validation", "blockers"],
    }
    return {
        "schema_version": "1.0",
        "supervisory_run_id": "DF4A-TEST",
        "parent_milestone": "DF.4A test",
        "objective": "Test isolated workspace preparation.",
        "workflow_state": "approved",
        "owner_approved_scope": ["Workspace preparation"],
        "expected_repository": {"branch": branch, "starting_head": head},
        "parent_permissions": {
            "code_changes": False,
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
                "exclusive_file_boundaries": ["docs/worker.md"],
                "shared_resources": [],
                "parallel_eligible": False,
                "escalation_flags": [],
                "workspace": {
                    "strategy": "isolated_worktree",
                    "workspace_id": "atlas-workspace",
                    "branch_hint": "lia/atlas-workspace",
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


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "factory@example.invalid")
    git(repo, "config", "user.name", "Development Factory")
    (repo / ".gitignore").write_text(".development-factory/\n", encoding="utf-8")
    roles = repo / "development-factory" / "agent-roles.json"
    roles.parent.mkdir()
    roles.write_text(json.dumps(roles_payload()), encoding="utf-8")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    git(repo, "add", ".gitignore", "development-factory/agent-roles.json", "README.md")
    git(repo, "commit", "-m", "fixture")
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(contract_payload(git(repo, "rev-parse", "HEAD"))),
        encoding="utf-8",
    )
    return repo, contract


def test_identity_and_path_are_deterministic(
    repository: tuple[Path, Path],
) -> None:
    repo, contract = repository
    manager = WorkspaceManager(repo)
    first = manager.load(contract, "atlas-workspace")[2]
    second = manager.load(contract, "atlas-workspace")[2]
    assert first == second
    assert Path(first.workspace_path).is_relative_to(
        repo / ".development-factory" / "workspaces"
    )
    assert first.workspace_branch.startswith("lia/df4a-test-")


def test_prepare_creates_verified_workspace_without_mutating_primary(
    repository: tuple[Path, Path],
) -> None:
    repo, contract = repository
    manager = WorkspaceManager(repo)
    starting_branch = git(repo, "branch", "--show-current")
    starting_head = git(repo, "rev-parse", "HEAD")

    metadata, reused = manager.prepare(contract, "atlas-workspace")

    assert reused is False
    assert metadata.identity.approved_starting_sha == starting_head
    assert metadata.validation_status == "not_run"
    assert manager.inspect(contract, "atlas-workspace").classification == "ready"
    assert manager.show(contract, "atlas-workspace") == metadata
    assert git(repo, "branch", "--show-current") == starting_branch
    assert git(repo, "rev-parse", "HEAD") == starting_head
    assert git(repo, "status", "--porcelain") == ""


def test_prepare_reuses_only_a_verified_workspace(
    repository: tuple[Path, Path],
) -> None:
    repo, contract = repository
    manager = WorkspaceManager(repo)
    created, _ = manager.prepare(contract, "atlas-workspace")
    reused, was_reused = manager.prepare(contract, "atlas-workspace")
    assert was_reused is True
    assert reused.created_at == created.created_at
    assert reused.identity == created.identity


@pytest.mark.parametrize("change", ["unstaged", "staged", "untracked"])
def test_workspace_content_is_classified_and_blocks_reuse(
    repository: tuple[Path, Path], change: str
) -> None:
    repo, contract = repository
    manager = WorkspaceManager(repo)
    metadata, _ = manager.prepare(contract, "atlas-workspace")
    workspace = Path(metadata.identity.workspace_path)
    if change == "untracked":
        (workspace / "new.txt").write_text("new\n", encoding="utf-8")
    else:
        readme = workspace / "README.md"
        readme.write_text("changed\n", encoding="utf-8")
        if change == "staged":
            git(workspace, "add", "README.md")

    inspection = manager.inspect(contract, "atlas-workspace")
    expected = "dirty" if change == "unstaged" else change
    assert inspection.classification == expected
    with pytest.raises(WorkspaceError, match="requires owner review"):
        manager.prepare(contract, "atlas-workspace")


def test_dirty_primary_repository_fails_closed(
    repository: tuple[Path, Path],
) -> None:
    repo, contract = repository
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")
    manager = WorkspaceManager(repo)
    inspection = manager.inspect(contract, "atlas-workspace")
    assert inspection.classification == "repository_diverged"
    with pytest.raises(WorkspaceError, match="working tree must be clean"):
        manager.prepare(contract, "atlas-workspace")


def test_wrong_branch_and_sha_fail_closed(repository: tuple[Path, Path]) -> None:
    repo, contract = repository
    manager = WorkspaceManager(repo)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload["expected_repository"]["branch"] = "other"
    payload["workers"][0]["task_contract"]["expected_repository"]["branch"] = "other"
    contract.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WorkspaceError, match="owner branch mismatch"):
        manager.prepare(contract, "atlas-workspace")

    payload["expected_repository"]["branch"] = "main"
    payload["workers"][0]["task_contract"]["expected_repository"]["branch"] = "main"
    payload["expected_repository"]["starting_head"] = "a" * 40
    payload["workers"][0]["task_contract"]["expected_repository"]["starting_head"] = (
        "a" * 40
    )
    contract.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WorkspaceError, match="owner HEAD mismatch"):
        manager.prepare(contract, "atlas-workspace")


def test_interrupted_and_orphaned_preparation_require_owner_review(
    repository: tuple[Path, Path],
) -> None:
    repo, contract = repository
    manager = WorkspaceManager(repo)
    identity = manager.load(contract, "atlas-workspace")[2]
    Path(identity.workspace_path).mkdir(parents=True)
    assert manager.inspect(contract, "atlas-workspace").classification == "interrupted"

    Path(identity.workspace_path).rmdir()
    metadata_path = manager._metadata_path(identity)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text("{}\n", encoding="utf-8")
    assert (
        manager.inspect(contract, "atlas-workspace").classification
        == "orphaned_metadata"
    )


def test_stale_head_and_duplicate_ownership_are_detected(
    repository: tuple[Path, Path],
) -> None:
    repo, contract = repository
    manager = WorkspaceManager(repo)
    metadata, _ = manager.prepare(contract, "atlas-workspace")
    workspace = Path(metadata.identity.workspace_path)
    (workspace / "worker.txt").write_text("change\n", encoding="utf-8")
    git(workspace, "add", "worker.txt")
    git(workspace, "commit", "-m", "unexpected worker commit")
    assert manager.inspect(contract, "atlas-workspace").classification == "stale"

    duplicate = repo / ".development-factory" / "workspace-metadata" / "duplicate.json"
    duplicate.write_text(
        json.dumps(
            {
                "identity": {
                    "workspace_id": metadata.identity.workspace_id,
                    "workspace_path": "/different",
                    "workspace_branch": "different",
                }
            }
        ),
        encoding="utf-8",
    )
    assert (
        manager.inspect(contract, "atlas-workspace").classification
        == "duplicate_ownership"
    )


def test_list_is_deterministic(repository: tuple[Path, Path]) -> None:
    repo, contract = repository
    inspections = WorkspaceManager(repo).list(contract)
    assert [item.identity.workspace_id for item in inspections] == ["atlas-workspace"]
    assert inspections[0].classification == "planned"
