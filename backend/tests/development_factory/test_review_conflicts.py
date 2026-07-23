from __future__ import annotations

from dataclasses import replace

from development_factory.lia_contract import (
    IsolationWorkspace,
    ResourceClaim,
    WorkerAssignment,
)
from development_factory.lia_planner import ExecutionPlan, ExecutionWave
from development_factory.review_conflicts import (
    consolidate_validation,
    detect_file_conflicts,
    detect_resource_conflicts,
    deterministic_review_order,
)
from development_factory.task_contract import StopConditions, TaskContract
from development_factory.workflow import ActionPermissions, WorkflowState


def worker(
    task_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    resource: ResourceClaim | None = None,
    role_id: str = "atlas",
) -> WorkerAssignment:
    task = TaskContract(
        schema_version="1.0",
        task_id=task_id,
        milestone="test",
        objective="test",
        workflow_state=WorkflowState.APPROVED,
        approved_scope=("review",),
        prohibited_scope=("privileged actions",),
        expected_branch="main",
        expected_starting_head="a" * 40,
        allowed_file_boundaries=(f"docs/{task_id}.md",),
        required_validation=("architecture",),
        permissions=ActionPermissions(),
        stop_conditions=StopConditions(True, True, True, True, True),
        required_report_fields=("validation",),
    )
    return WorkerAssignment(
        agent_id=f"agent-{task_id}",
        role_id=role_id,
        task=task,
        depends_on=depends_on,
        exclusive_file_boundaries=(f"docs/{task_id}.md",),
        shared_resources=(resource,) if resource else (),
        parallel_eligible=True,
        escalation_flags=(),
        workspace=IsolationWorkspace(
            "isolated_worktree", f"workspace-{task_id}", f"lia/{task_id}"
        ),
    )


def test_file_conflicts_detect_exact_case_and_parent_collisions() -> None:
    workers = {"A": worker("A"), "B": worker("B")}
    conflicts = detect_file_conflicts(
        {
            "A": ("docs/Shared.md", "docs/tree"),
            "B": ("docs/shared.md", "docs/tree/child.md"),
        },
        workers,
    )
    assert [item.classification for item in conflicts] == [
        "prohibited_overlap",
        "prohibited_overlap",
    ]
    assert "case-normalization" in conflicts[0].rationale
    assert "parent/child" in conflicts[1].rationale


def test_dependency_overlap_is_ordered_but_not_resolved() -> None:
    workers = {"A": worker("A"), "B": worker("B", depends_on=("A",))}
    conflict = detect_file_conflicts(
        {"A": ("docs/shared.md",), "B": ("docs/shared.md",)}, workers
    )[0]
    assert conflict.classification == "ordered_dependency"


def test_typed_resource_conflicts_are_deterministic() -> None:
    exclusive = ResourceClaim("shared_schema", "public-contract", "exclusive")
    left = worker("A", resource=exclusive)
    right = worker("B", resource=replace(exclusive, mode="shared"))
    conflict = detect_resource_conflicts((left, right))[0]
    assert conflict.classification == "prohibited_overlap"

    shared = ResourceClaim("documentation", "guide", "shared")
    ordered = detect_resource_conflicts(
        (
            worker("A", resource=shared),
            worker("B", depends_on=("A",), resource=shared),
        )
    )[0]
    assert ordered.classification == "ordered_dependency"


def test_validation_consolidation_detects_missing_failed_and_redaction() -> None:
    summary = consolidate_validation(
        "A",
        ("architecture", "backend"),
        {
            "secret_redaction_result": "applied",
            "validation_results": [
                {
                    "selection": "architecture",
                    "exit_classification": "passed",
                    "blocks_completion": False,
                }
            ],
        },
    )
    assert summary.passed == ("architecture",)
    assert summary.missing == ("backend",)
    assert summary.redacted is True


def test_review_order_prioritizes_blockers_resources_and_roles() -> None:
    workers = {
        "BACKEND": worker("BACKEND", role_id="atlas"),
        "SECURITY": worker(
            "SECURITY",
            role_id="sentinel",
            resource=ResourceClaim("security_surface", "auth", "exclusive"),
        ),
        "TEST": worker("TEST", role_id="scout"),
    }
    plan = ExecutionPlan(
        workers=(),
        waves=(ExecutionWave(1, ("BACKEND", "SECURITY", "TEST")),),
    )
    order = deterministic_review_order(
        plan,
        workers,
        {
            "BACKEND": "verified_ready_for_review",
            "SECURITY": "verified_review_required",
            "TEST": "blocked_validation",
        },
    )
    assert [item[0] for item in order] == ["TEST", "SECURITY", "BACKEND"]
