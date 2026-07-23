from __future__ import annotations

import copy
import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from development_factory.owner_review import OwnerReviewManager
from development_factory.review_records import canonical_digest
from development_factory.worker_execution import WorkerExecutor
from development_factory.worker_records import load_worker_record_payload
from development_factory.workspaces import WorkspaceManager


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="end-to-end factory demonstration requires the Git executable",
)


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def contract_payload(head: str) -> dict[str, Any]:
    task = {
        "schema_version": "1.0",
        "task_id": "DF4D-PROOF",
        "milestone": "DF.4D deterministic demonstration",
        "objective": "Create one bounded documentation proof.",
        "workflow_state": "approved",
        "approved_scope": ["One temporary documentation change"],
        "prohibited_scope": ["Integration", "Privileged actions", "Network"],
        "expected_repository": {"branch": "main", "starting_head": head},
        "allowed_file_boundaries": ["docs/factory-proof.md"],
        "required_validation": ["architecture"],
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
            "validation",
            "changed_files",
            "blockers",
        ],
    }
    return {
        "schema_version": "1.0",
        "supervisory_run_id": "DF4D-DEMONSTRATION",
        "parent_milestone": "DF.4D deterministic demonstration",
        "objective": "Prove the factory stops at consolidated owner review.",
        "workflow_state": "approved",
        "owner_approved_scope": ["One temporary documentation change"],
        "expected_repository": {"branch": "main", "starting_head": head},
        "parent_permissions": {
            "code_changes": True,
            "stage_and_commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
        },
        "parallel_execution_approved": False,
        "workers": [
            {
                "agent_id": "atlas-proof-worker",
                "role_id": "atlas",
                "task_contract": task,
                "depends_on": [],
                "exclusive_file_boundaries": ["docs/factory-proof.md"],
                "shared_resources": [
                    {
                        "resource_type": "documentation",
                        "resource_id": "df4d-proof",
                        "mode": "exclusive",
                    }
                ],
                "parallel_eligible": False,
                "escalation_flags": [],
                "workspace": {
                    "strategy": "isolated_worktree",
                    "workspace_id": "df4d-proof-workspace",
                    "branch_hint": "lia/df4d-proof",
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


def operations_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "execution_id": "DF4D-PROOF-EXECUTION",
        "task_id": "DF4D-PROOF",
        "workspace_id": "df4d-proof-workspace",
        "allowed_action_classes": ["mutation", "validation"],
        "operations": [
            {
                "operation_id": "create-proof",
                "operation": "create_demonstration_file",
                "path": "docs/factory-proof.md",
                "paths": [],
                "text": "# Deterministic factory proof\n",
                "expected_text": None,
                "replacement_text": None,
                "resource_type": "documentation",
                "resource_id": "df4d-proof",
            }
        ],
        "validation_selections": ["architecture"],
        "termination_policy": {
            "maximum_operations": 1,
            "maximum_mutations": 1,
            "maximum_files_inspected": 1,
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


def create_repository(root: Path) -> tuple[Path, Path, Path]:
    repo = root / "supervising-repository"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "factory@example.invalid")
    git(repo, "config", "user.name", "Development Factory")
    source = Path(__file__).parents[3]
    (repo / ".gitignore").write_text(".development-factory/\n", encoding="utf-8")
    factory = repo / "development-factory"
    factory.mkdir()
    for name in ("agent-roles.json", "config.json", "manifest.json"):
        shutil.copy(source / "development-factory" / name, factory / name)
    (repo / "docs").mkdir()
    (repo / "docs/source.md").write_text("# source\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture baseline")
    head = git(repo, "rev-parse", "HEAD")
    contract_value = contract_payload(head)
    contract = root / "supervisory-contract.json"
    contract.write_text(json.dumps(contract_value), encoding="utf-8")
    operations = root / "worker-operations.json"
    operations.write_text(json.dumps(operations_payload()), encoding="utf-8")
    return repo, contract, operations


def consolidation_payload(
    contract: dict[str, Any], worker_record: Path
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "review_id": "DF4D-PROOF-REVIEW",
        "supervisory_run_id": contract["supervisory_run_id"],
        "parent_milestone": contract["parent_milestone"],
        "parent_objective": contract["objective"],
        "approved_repository": {
            "branch": contract["expected_repository"]["branch"],
            "starting_sha": contract["expected_repository"]["starting_head"],
        },
        "supervisory_contract_digest": canonical_digest(contract),
        "included_worker_task_ids": ["DF4D-PROOF"],
        "worker_records": [str(worker_record)],
        "required_execution_waves": [["DF4D-PROOF"]],
        "required_dependency_evidence": True,
        "required_validation_evidence": ["architecture"],
        "review_policy": {
            "require_all_workers": True,
            "allow_incomplete_downstream_review": False,
            "security_sensitive_owner_review": True,
        },
        "conflict_policy": "fail_closed",
        "stop_policy": ["Stop on provenance mismatch"],
        "required_owner_decision_fields": [
            "decision_type",
            "rationale",
            "review_digest",
        ],
    }


def test_end_to_end_factory_demonstration_stops_at_owner_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active_repo = Path(__file__).parents[3]
    active_before = git(active_repo, "status", "--porcelain=v1")
    demonstration_root = tmp_path / "factory-demonstration"
    demonstration_root.mkdir()
    repo, contract, operations = create_repository(demonstration_root)
    baseline = git(repo, "rev-parse", "HEAD")
    primary_before = git(repo, "status", "--porcelain=v1")

    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the deterministic demonstration attempted network access")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    metadata, reused = WorkspaceManager(repo).prepare(contract, "df4d-proof-workspace")
    assert reused is False
    workspace = Path(metadata.identity.workspace_path)
    assert workspace.exists()
    assert git(workspace, "rev-parse", "HEAD") == baseline

    record, record_path, markdown_path = WorkerExecutor(repo).execute(
        contract, "DF4D-PROOF", operations
    )
    assert record.recommended_worker_state == "completed"
    assert record.provenance.integration_state == "not_integrated"
    assert record.provenance.approval_state == "owner_review_required"
    assert record.validation_results[0].exit_classification == "passed"
    assert record_path.exists() and markdown_path.exists()
    assert (workspace / "docs/factory-proof.md").exists()

    contract_value = json.loads(contract.read_text())
    request = demonstration_root / "consolidation.json"
    request.write_text(
        json.dumps(consolidation_payload(contract_value, record_path)),
        encoding="utf-8",
    )
    review, review_path, review_markdown = OwnerReviewManager(repo).consolidate(
        contract, request
    )
    worker_review = review.worker_reviews[0]
    assert worker_review.classification == "verified_ready_for_review"
    assert worker_review.approval_state == "owner_review_required"
    assert worker_review.integration_state == "not_integrated"
    assert worker_review.provenance_manifest_digest == (
        record.provenance.manifest_digest
    )
    assert review.evidence_chain_digest
    assert review.state_history[-1] == "owner_review_required"
    assert review.recorded_owner_decisions == ()
    assert review_path.exists() and review_markdown.exists()

    assert git(repo, "rev-parse", "HEAD") == baseline
    assert git(repo, "status", "--porcelain=v1") == primary_before
    assert not (repo / "docs/factory-proof.md").exists()
    assert git(workspace, "diff", "--name-only") == ""
    assert git(workspace, "ls-files", "--others", "--exclude-standard") == (
        "docs/factory-proof.md"
    )
    assert git(active_repo, "status", "--porcelain=v1") == active_before


def test_provenance_digest_and_identity_fail_closed(tmp_path: Path) -> None:
    repo, contract, operations = create_repository(tmp_path)
    WorkspaceManager(repo).prepare(contract, "df4d-proof-workspace")
    _, record_path, _ = WorkerExecutor(repo).execute(contract, "DF4D-PROOF", operations)
    original = json.loads(record_path.read_text())

    mutations = (
        ("assignment", ("provenance", "assignment_id"), "UNRELATED"),
        ("workspace", ("workspace_id",), "UNRELATED"),
        (
            "digest",
            ("provenance", "output_manifest_digest"),
            "0" * 64,
        ),
    )
    for label, keys, value in mutations:
        payload = copy.deepcopy(original)
        target = payload
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
        path = tmp_path / f"{label}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError):
            load_worker_record_payload(path)

    missing = copy.deepcopy(original)
    del missing["provenance"]
    missing_path = tmp_path / "missing.json"
    missing_path.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(ValueError, match="fields are invalid"):
        load_worker_record_payload(missing_path)

    outside = copy.deepcopy(original)
    outside["provenance"]["output_files"][0]["path"] = "outside-boundary.md"
    outside["provenance"]["output_manifest_digest"] = canonical_digest(
        outside["provenance"]["output_files"]
    )
    manifest = {
        key: value
        for key, value in outside["provenance"].items()
        if key != "manifest_digest"
    }
    outside["provenance"]["manifest_digest"] = canonical_digest(manifest)
    outside_path = tmp_path / "outside.json"
    outside_path.write_text(json.dumps(outside), encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds declared boundary"):
        load_worker_record_payload(outside_path)

    approved = copy.deepcopy(original)
    approved["provenance"]["approval_state"] = "approved"
    approved_path = tmp_path / "self-approved.json"
    approved_path.write_text(json.dumps(approved), encoding="utf-8")
    with pytest.raises(ValueError, match="approval_state mismatch"):
        load_worker_record_payload(approved_path)

    missing_reference = copy.deepcopy(original)
    missing_reference["provenance"]["artifact_references"] = []
    manifest = {
        key: value
        for key, value in missing_reference["provenance"].items()
        if key != "manifest_digest"
    }
    missing_reference["provenance"]["manifest_digest"] = canonical_digest(manifest)
    missing_reference_path = tmp_path / "missing-reference.json"
    missing_reference_path.write_text(json.dumps(missing_reference), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact references are missing"):
        load_worker_record_payload(missing_reference_path)


def test_unrelated_worker_record_cannot_enter_owner_review(tmp_path: Path) -> None:
    repo, contract, operations = create_repository(tmp_path)
    WorkspaceManager(repo).prepare(contract, "df4d-proof-workspace")
    _, record_path, markdown_path = WorkerExecutor(repo).execute(
        contract, "DF4D-PROOF", operations
    )
    unrelated_payload = json.loads(record_path.read_text())
    unrelated_payload["supervisory_run_id"] = "UNRELATED-RUN"
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text(json.dumps(unrelated_payload), encoding="utf-8")
    unrelated.with_suffix(".md").write_text(
        markdown_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    contract_value = json.loads(contract.read_text())
    request = tmp_path / "unrelated-consolidation.json"
    request.write_text(
        json.dumps(consolidation_payload(contract_value, unrelated)),
        encoding="utf-8",
    )
    review, _, _ = OwnerReviewManager(repo).consolidate(contract, request)
    assert review.worker_reviews[0].classification == "missing_record"
    assert any("supervisory run mismatch" in item for item in review.blockers)
    assert review.worker_reviews[0].integration_state == "not_integrated"
