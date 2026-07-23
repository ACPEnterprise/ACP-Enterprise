from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from development_factory.owner_review import (
    ConsolidationState,
    OwnerReviewError,
    OwnerReviewManager,
    transition_consolidation,
)
from development_factory.review_records import (
    ReviewRecordError,
    canonical_digest,
    file_digest,
    load_consolidation_input,
    load_owner_decision,
)
from development_factory.worker_execution import WorkerExecutor
from development_factory.workspaces import WorkspaceManager


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="real consolidation lifecycle tests require the Git executable",
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


def worker(task_id: str, *, depends_on: list[str]) -> dict[str, Any]:
    scope = ["Documentation review", "Bounded documentation mutation"]
    return {
        "agent_id": f"atlas-{task_id.lower()}",
        "role_id": "atlas",
        "task_contract": {
            "schema_version": "1.0",
            "task_id": task_id,
            "milestone": "DF.4C demonstration",
            "objective": f"Create {task_id} documentation evidence.",
            "workflow_state": "approved",
            "approved_scope": scope,
            "prohibited_scope": ["Privileged actions", "Integration"],
            "expected_repository": {"branch": "main", "starting_head": ""},
            "allowed_file_boundaries": [f"docs/{task_id}.md"],
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
            "required_report_fields": ["validation", "changed_files", "blockers"],
        },
        "depends_on": depends_on,
        "exclusive_file_boundaries": [f"docs/{task_id}.md"],
        "shared_resources": [
            {
                "resource_type": "documentation",
                "resource_id": f"document-{task_id}",
                "mode": "exclusive",
            }
        ],
        "parallel_eligible": not depends_on,
        "escalation_flags": [],
        "workspace": {
            "strategy": "isolated_worktree",
            "workspace_id": f"workspace-{task_id.lower()}",
            "branch_hint": f"lia/{task_id.lower()}",
        },
    }


def contract_payload(head: str) -> dict[str, Any]:
    workers = [
        worker("DOC-A", depends_on=[]),
        worker("DOC-B", depends_on=[]),
        worker("DOC-C", depends_on=["DOC-A", "DOC-B"]),
    ]
    for item in workers:
        item["task_contract"]["expected_repository"]["starting_head"] = head
    return {
        "schema_version": "1.0",
        "supervisory_run_id": "DF4C-DEMO",
        "parent_milestone": "DF.4C demonstration",
        "objective": "Consolidate three fictional documentation workers.",
        "workflow_state": "approved",
        "owner_approved_scope": [
            "Documentation review",
            "Bounded documentation mutation",
        ],
        "expected_repository": {"branch": "main", "starting_head": head},
        "parent_permissions": {
            "code_changes": True,
            "stage_and_commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
        },
        "parallel_execution_approved": True,
        "workers": workers,
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


def operations(task_id: str, execution_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "execution_id": execution_id,
        "task_id": task_id,
        "workspace_id": f"workspace-{task_id.lower()}",
        "allowed_action_classes": ["mutation", "validation"],
        "operations": [
            {
                "operation_id": f"create-{task_id.lower()}",
                "operation": "create_demonstration_file",
                "path": f"docs/{task_id}.md",
                "paths": [],
                "text": f"# {task_id}\n",
                "expected_text": None,
                "replacement_text": None,
                "resource_type": "documentation",
                "resource_id": f"document-{task_id}",
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
        "required_report_fields": ["validation_results", "action_audit"],
    }


def consolidation_payload(
    contract_payload_value: dict[str, Any],
    record_paths: list[Path],
    *,
    review_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "review_id": review_id,
        "supervisory_run_id": "DF4C-DEMO",
        "parent_milestone": "DF.4C demonstration",
        "parent_objective": "Consolidate three fictional documentation workers.",
        "approved_repository": {
            "branch": "main",
            "starting_sha": contract_payload_value["expected_repository"][
                "starting_head"
            ],
        },
        "supervisory_contract_digest": canonical_digest(contract_payload_value),
        "included_worker_task_ids": ["DOC-A", "DOC-B", "DOC-C"],
        "worker_records": [str(path) for path in record_paths],
        "required_execution_waves": [["DOC-A", "DOC-B"], ["DOC-C"]],
        "required_dependency_evidence": True,
        "required_validation_evidence": ["architecture"],
        "review_policy": {
            "require_all_workers": True,
            "allow_incomplete_downstream_review": False,
            "security_sensitive_owner_review": True,
        },
        "conflict_policy": "fail_closed",
        "stop_policy": ["provenance", "security", "privileged_action"],
        "required_owner_decision_fields": [
            "decision_type",
            "rationale",
            "review_digest",
        ],
    }


@pytest.fixture
def demonstration(tmp_path: Path) -> dict[str, Any]:
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
    (repo / "docs").mkdir()
    (repo / "docs/source.md").write_text("# source\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    head = git(repo, "rev-parse", "HEAD")
    contract_value = contract_payload(head)
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(contract_value), encoding="utf-8")
    workspace_manager = WorkspaceManager(repo)
    executor = WorkerExecutor(repo)
    record_paths: list[Path] = []
    for index, task_id in enumerate(("DOC-A", "DOC-B", "DOC-C"), start=1):
        workspace_manager.prepare(contract, f"workspace-{task_id.lower()}")
        operation_path = tmp_path / f"{task_id}.json"
        operation_path.write_text(
            json.dumps(operations(task_id, f"EXEC-{index}")), encoding="utf-8"
        )
        record, record_path, _ = executor.execute(contract, task_id, operation_path)
        assert record.recommended_worker_state == "completed"
        record_paths.append(record_path)
    consolidation = tmp_path / "consolidation.json"
    consolidation.write_text(
        json.dumps(
            consolidation_payload(contract_value, record_paths, review_id="REVIEW-1")
        ),
        encoding="utf-8",
    )
    return {
        "repo": repo,
        "contract": contract,
        "contract_value": contract_value,
        "consolidation": consolidation,
        "record_paths": record_paths,
    }


def test_consolidation_state_transitions_fail_closed() -> None:
    assert (
        transition_consolidation(
            ConsolidationState.PENDING, ConsolidationState.RECORDS_LOADING
        )
        == ConsolidationState.RECORDS_LOADING
    )
    with pytest.raises(OwnerReviewError, match="invalid consolidation transition"):
        transition_consolidation(
            ConsolidationState.PENDING, ConsolidationState.COMPLETED
        )


def test_successful_three_worker_consolidation_and_package(
    demonstration: dict[str, Any],
) -> None:
    manager = OwnerReviewManager(demonstration["repo"])
    review, json_path, markdown_path = manager.consolidate(
        demonstration["contract"], demonstration["consolidation"]
    )
    assert [item.classification for item in review.worker_reviews] == [
        "verified_ready_for_review",
        "verified_ready_for_review",
        "verified_ready_for_review",
    ]
    assert review.execution_waves == (("DOC-A", "DOC-B"), ("DOC-C",))
    assert review.blockers == ()
    assert review.state_history[-1] == "owner_review_required"
    assert review.action_audit.files_modified_by_consolidator is False
    assert json_path.exists() and markdown_path.exists()
    assert "What LIA did not do" in markdown_path.read_text()
    assert git(demonstration["repo"], "status", "--porcelain") == ""
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "development-factory/consolidated-owner-review.schema.json"
        ).read_text()
    )
    assert set(review.to_dict()) == set(schema["required"])


def test_provenance_mismatch_blocks_without_repair(
    demonstration: dict[str, Any],
) -> None:
    repo = demonstration["repo"]
    contract = demonstration["contract"]
    manager = WorkspaceManager(repo)
    identity = manager.load(contract, "workspace-doc-a")[2]
    path = Path(identity.workspace_path) / "docs/DOC-A.md"
    path.write_text("# changed after record\n", encoding="utf-8")
    payload = consolidation_payload(
        demonstration["contract_value"],
        demonstration["record_paths"],
        review_id="REVIEW-DRIFT",
    )
    request = contract.parent / "drift.json"
    request.write_text(json.dumps(payload), encoding="utf-8")
    review, _, _ = OwnerReviewManager(repo).consolidate(contract, request)
    first = {item.task_id: item for item in review.worker_reviews}["DOC-A"]
    assert first.classification == "blocked_provenance"
    assert "changed after record finalization" in first.provenance_findings[0]
    assert path.read_text() == "# changed after record\n"


def test_missing_partial_malformed_duplicate_and_privileged_records_fail_closed(
    demonstration: dict[str, Any],
    tmp_path: Path,
) -> None:
    base = consolidation_payload(
        demonstration["contract_value"],
        demonstration["record_paths"],
        review_id="REVIEW-INVALID",
    )
    base["worker_records"] = base["worker_records"][:-1]
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    review, _, _ = OwnerReviewManager(demonstration["repo"]).consolidate(
        demonstration["contract"], path
    )
    assert "DOC-C" in review.excluded_or_missing_workers

    malformed = tmp_path / "malformed-record.json"
    malformed.write_text("{}\n", encoding="utf-8")
    base["review_id"] = "REVIEW-MALFORMED"
    base["worker_records"] = [str(malformed)]
    path.write_text(json.dumps(base), encoding="utf-8")
    review, _, _ = OwnerReviewManager(demonstration["repo"]).consolidate(
        demonstration["contract"], path
    )
    assert any("malformed worker record" in item for item in review.blockers)

    privileged_payload = json.loads(demonstration["record_paths"][0].read_text())
    privileged_payload["action_audit"]["committed_by_factory"] = True
    privileged = tmp_path / "privileged.json"
    privileged.write_text(json.dumps(privileged_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="privileged action"):
        from development_factory.worker_records import load_worker_record_payload

        load_worker_record_payload(privileged)


def test_consolidation_cannot_weaken_required_evidence(
    demonstration: dict[str, Any],
) -> None:
    payload = consolidation_payload(
        demonstration["contract_value"],
        demonstration["record_paths"],
        review_id="REVIEW-WEAK-EVIDENCE",
    )
    payload["required_dependency_evidence"] = False
    payload["required_validation_evidence"] = ["frontend"]
    request = demonstration["contract"].parent / "weak-evidence.json"
    request.write_text(json.dumps(payload), encoding="utf-8")
    issues = OwnerReviewManager(demonstration["repo"]).inspect(
        demonstration["contract"], request
    )
    assert "consolidation cannot disable dependency evidence" in issues
    assert "consolidation validation evidence differs from worker contracts" in issues


def test_review_immutability_cancellation_and_owner_decision(
    demonstration: dict[str, Any], tmp_path: Path
) -> None:
    manager = OwnerReviewManager(demonstration["repo"])
    review, review_path, _ = manager.consolidate(
        demonstration["contract"], demonstration["consolidation"]
    )
    with pytest.raises(OwnerReviewError, match="finalized package"):
        manager.consolidate(demonstration["contract"], demonstration["consolidation"])
    decision_payload = {
        "schema_version": "1.0",
        "decision_id": "DECISION-1",
        "supervisory_run_id": "DF4C-DEMO",
        "review_id": review.review_id,
        "worker_task_id": "DOC-A",
        "decision_type": "accept_for_continued_review",
        "decision_status": "recorded",
        "rationale": "Continue review only; token=do-not-store",
        "timestamp": "2026-07-23T12:00:00+00:00",
        "review_digest": file_digest(review_path),
        "permits_further_planning_only": True,
        "privileged_action_audit": {
            field: False for field in review.action_audit.__dataclass_fields__
        },
    }
    decision = tmp_path / "decision.json"
    decision.write_text(json.dumps(decision_payload), encoding="utf-8")
    decision_path = manager.record_decision(
        demonstration["contract"], review.review_id, decision
    )
    assert "do-not-store" not in decision_path.read_text()
    cancellation = manager.cancel(demonstration["contract"], review.review_id)
    assert json.loads(cancellation.read_text())["worker_outputs_preserved"] is True

    stale = copy.deepcopy(decision_payload)
    stale["decision_id"] = "DECISION-STALE"
    stale["review_digest"] = "0" * 64
    decision.write_text(json.dumps(stale), encoding="utf-8")
    with pytest.raises(OwnerReviewError, match="stale review evidence"):
        manager.record_decision(demonstration["contract"], review.review_id, decision)


def test_strict_examples_parse_or_validate_shape(tmp_path: Path) -> None:
    root = Path(__file__).parents[3] / "development-factory/examples"
    request = load_consolidation_input(root / "df4c-consolidation-input.json")
    assert request.review_id == "DF4C-DEMO-REVIEW"
    decision = load_owner_decision(root / "df4c-owner-decision.json")
    assert decision.permits_further_planning_only is True
    unknown = json.loads((root / "df4c-consolidation-input.json").read_text())
    unknown["unexpected"] = True
    path = tmp_path / "invalid-consolidation.json"
    path.write_text(json.dumps(unknown), encoding="utf-8")
    with pytest.raises(ReviewRecordError, match="fields are invalid"):
        load_consolidation_input(path)
