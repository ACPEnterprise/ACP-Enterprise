from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from development_factory.lia import LiaSupervisor
from development_factory.lia_contract import (
    LiaContractError,
    parse_lia_contract,
)
from development_factory.lia_planner import (
    WorkerOutcome,
    build_integration_plan,
    plan_execution,
)
from development_factory.lia_reports import (
    LIA_REPORT_VERSION,
    LiaSupervisoryReport,
    SupervisoryWorkerReport,
    planned_integration,
    render_supervisory_markdown,
    write_supervisory_report,
)
from development_factory.lia_roles import AgentRole, AgentRoleError, load_agent_roles
from development_factory.models import RepositoryState
from development_factory.run_records import RunActionAudit
from development_factory.workflow import Action, WorkflowError


HEAD = "a" * 40


def role_catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "roles": [
            {
                "role_id": role_id,
                "display_name": role_id.title(),
                "responsibilities": [f"{role_id} responsibility"],
                "prohibited_responsibilities": ["Privileged actions"],
                "default_validation": ["architecture"],
                "escalation_conditions": ["Boundary is unclear"],
                "may_propose_code_changes": role_id != "scout",
                "may_review_other_work": True,
                "privileged_authority": {
                    "commit": False,
                    "push": False,
                    "merge": False,
                    "deployment": False,
                },
            }
            for role_id in ("atlas", "nova", "forge", "sentinel", "scout")
        ],
    }


def write_roles(path: Path) -> None:
    path.write_text(json.dumps(role_catalog_payload()), encoding="utf-8")


def task(task_id: str, scope: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "milestone": task_id,
        "objective": f"Complete {task_id}.",
        "workflow_state": "approved",
        "approved_scope": scope or ["inspection"],
        "prohibited_scope": ["privileged actions"],
        "expected_repository": {
            "branch": "customer-management-v1",
            "starting_head": HEAD,
        },
        "allowed_file_boundaries": [],
        "required_validation": ["architecture"],
        "permissions": {
            "code_changes": False,
            "stage_and_commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
        },
        "stop_conditions": {
            "require_clean_start": False,
            "require_empty_index": True,
            "stop_on_branch_mismatch": True,
            "stop_on_head_mismatch": True,
            "stop_on_unapproved_files": True,
        },
        "required_report_fields": ["validation", "blockers"],
    }


def worker(
    task_id: str,
    agent_id: str,
    role_id: str,
    *,
    depends_on: list[str] | None = None,
    file_boundary: str | None = None,
    resources: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "role_id": role_id,
        "task_contract": task(task_id),
        "depends_on": depends_on or [],
        "exclusive_file_boundaries": [file_boundary or f"docs/{task_id}.md"],
        "shared_resources": resources or [],
        "parallel_eligible": True,
        "escalation_flags": [],
        "workspace": {
            "strategy": "isolated_worktree",
            "workspace_id": f"workspace-{agent_id}",
            "branch_hint": f"lia/{agent_id}",
        },
    }


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "supervisory_run_id": "LIA-TEST",
        "parent_milestone": "DF.3 test",
        "objective": "Test deterministic supervision.",
        "workflow_state": "approved",
        "owner_approved_scope": ["inspection"],
        "expected_repository": {
            "branch": "customer-management-v1",
            "starting_head": HEAD,
        },
        "parent_permissions": {
            "code_changes": False,
            "stage_and_commit": False,
            "push": False,
            "merge": False,
            "deployment": False,
        },
        "parallel_execution_approved": True,
        "workers": [
            worker("TASK-A", "atlas-one", "atlas"),
            worker("TASK-B", "nova-one", "nova"),
            worker(
                "TASK-C",
                "scout-one",
                "scout",
                depends_on=["TASK-A", "TASK-B"],
            ),
        ],
        "validation_requirements": ["all"],
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
def roles(tmp_path: Path) -> dict[str, AgentRole]:
    path = tmp_path / "agent-roles.json"
    write_roles(path)
    return load_agent_roles(path)


def test_agent_roles_are_strict_and_have_no_privileged_authority(
    tmp_path: Path,
) -> None:
    path = tmp_path / "agent-roles.json"
    write_roles(path)
    roles = load_agent_roles(path)
    assert set(roles) == {"atlas", "nova", "forge", "sentinel", "scout"}
    assert all(role.responsibilities for role in roles.values())
    assert all(role.escalation_conditions for role in roles.values())
    assert all(
        not any((role.may_commit, role.may_push, role.may_merge, role.may_deploy))
        for role in roles.values()
    )


def test_agent_role_catalog_rejects_privileged_authority(
    tmp_path: Path,
) -> None:
    payload = role_catalog_payload()
    payload["roles"][0]["privileged_authority"]["commit"] = True
    path = tmp_path / "roles.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AgentRoleError, match="privileged authority"):
        load_agent_roles(path)


def test_valid_contract_and_execution_waves(roles: dict[str, AgentRole]) -> None:
    contract = parse_lia_contract(contract_payload(), roles)
    plan = plan_execution(contract)
    assert plan.waves[0].task_ids == ("TASK-A", "TASK-B")
    assert plan.waves[1].task_ids == ("TASK-C",)
    eligibility = {item.task_id: item.eligibility for item in plan.workers}
    assert eligibility == {
        "TASK-A": "parallel_safe",
        "TASK-B": "parallel_safe",
        "TASK-C": "sequential_required",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_task", "duplicate worker task_id"),
        ("duplicate_agent", "duplicate worker agent_id"),
        ("unknown_dependency", "unknown dependencies"),
        ("cycle", "contains a cycle"),
        ("file_overlap", "exclusive file ownership conflict"),
        ("workspace_overlap", "workspace IDs must be unique"),
    ],
)
def test_invalid_decomposition_fails_closed(
    roles: dict[str, AgentRole], mutation: str, message: str
) -> None:
    payload = contract_payload()
    workers = payload["workers"]
    assert isinstance(workers, list)
    if mutation == "duplicate_task":
        workers[1]["task_contract"]["task_id"] = "TASK-A"
    elif mutation == "duplicate_agent":
        workers[1]["agent_id"] = "atlas-one"
    elif mutation == "unknown_dependency":
        workers[2]["depends_on"] = ["UNKNOWN"]
    elif mutation == "cycle":
        workers[0]["depends_on"] = ["TASK-C"]
        workers[2]["depends_on"] = ["TASK-A"]
    elif mutation == "file_overlap":
        workers[1]["exclusive_file_boundaries"] = ["docs/TASK-A.md"]
    else:
        workers[1]["workspace"]["workspace_id"] = "workspace-atlas-one"
    with pytest.raises(LiaContractError, match=message):
        parse_lia_contract(payload, roles)


@pytest.mark.parametrize(
    "resource_type", ["migration", "shared_schema", "integration_surface"]
)
def test_exclusive_shared_resource_conflicts_fail_closed(
    roles: dict[str, AgentRole], resource_type: str
) -> None:
    payload = contract_payload()
    workers = payload["workers"]
    assert isinstance(workers, list)
    claim = {
        "resource_type": resource_type,
        "resource_id": "authoritative-surface",
        "mode": "exclusive",
    }
    workers[0]["shared_resources"] = [claim]
    workers[1]["shared_resources"] = [copy.deepcopy(claim)]
    with pytest.raises(LiaContractError, match="ownership conflict"):
        parse_lia_contract(payload, roles)


def test_shared_resource_users_are_sequenced(roles: dict[str, AgentRole]) -> None:
    payload = contract_payload()
    workers = payload["workers"]
    assert isinstance(workers, list)
    claim = {
        "resource_type": "documentation",
        "resource_id": "common-index",
        "mode": "shared",
    }
    workers[0]["shared_resources"] = [claim]
    workers[1]["shared_resources"] = [copy.deepcopy(claim)]
    contract = parse_lia_contract(payload, roles)
    assert plan_execution(contract).waves[:2] == (
        plan_execution(contract).waves[0],
        plan_execution(contract).waves[1],
    )
    assert plan_execution(contract).waves[0].task_ids == ("TASK-A",)
    assert plan_execution(contract).waves[1].task_ids == ("TASK-B",)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("scope", "scope exceeds parent"),
        ("branch", "branch mismatch"),
        ("head", "starting HEAD mismatch"),
        ("permission", "permission stage_and_commit exceeds parent"),
        ("unknown_role", "unknown agent role"),
        ("validation", "unsupported area"),
    ],
)
def test_parent_inheritance_and_worker_contracts_fail_closed(
    roles: dict[str, AgentRole], mutation: str, message: str
) -> None:
    payload = contract_payload()
    workers = payload["workers"]
    assert isinstance(workers, list)
    task_payload = workers[0]["task_contract"]
    if mutation == "scope":
        task_payload["approved_scope"] = ["outside"]
    elif mutation == "branch":
        task_payload["expected_repository"]["branch"] = "wrong"
    elif mutation == "head":
        task_payload["expected_repository"]["starting_head"] = "b" * 40
    elif mutation == "permission":
        task_payload["permissions"]["stage_and_commit"] = True
    elif mutation == "unknown_role":
        workers[0]["role_id"] = "unrestricted"
    else:
        task_payload["required_validation"] = ["unsupported"]
    with pytest.raises(LiaContractError, match=message):
        parse_lia_contract(payload, roles)


def test_parent_parallel_policy_forces_sequential_waves(
    roles: dict[str, AgentRole],
) -> None:
    payload = contract_payload()
    payload["parallel_execution_approved"] = False
    contract = parse_lia_contract(payload, roles)
    assert all(len(wave.task_ids) == 1 for wave in plan_execution(contract).waves)


def test_worker_parallel_opt_out_forces_its_own_wave(
    roles: dict[str, AgentRole],
) -> None:
    payload = contract_payload()
    workers = payload["workers"]
    assert isinstance(workers, list)
    workers[0]["parallel_eligible"] = False
    contract = parse_lia_contract(payload, roles)
    assert plan_execution(contract).waves[0].task_ids == ("TASK-A",)
    assert plan_execution(contract).waves[1].task_ids == ("TASK-B",)


def test_parent_validation_and_report_fields_are_strict(
    roles: dict[str, AgentRole],
) -> None:
    payload = contract_payload()
    payload["validation_requirements"] = ["unsupported"]
    with pytest.raises(LiaContractError, match="unsupported area"):
        parse_lia_contract(payload, roles)
    payload = contract_payload()
    payload["required_report_fields"] = ["unknown"]
    with pytest.raises(LiaContractError, match="unsupported fields"):
        parse_lia_contract(payload, roles)


def test_escalation_flag_requires_owner_review(
    roles: dict[str, AgentRole],
) -> None:
    payload = contract_payload()
    workers = payload["workers"]
    assert isinstance(workers, list)
    workers[0]["escalation_flags"] = ["security boundary unclear"]
    contract = parse_lia_contract(payload, roles)
    planned = {item.task_id: item for item in plan_execution(contract).workers}
    assert planned["TASK-A"].eligibility == "owner_review_required"


def test_integration_plan_is_advisory_and_dependency_ordered(
    roles: dict[str, AgentRole],
) -> None:
    contract = parse_lia_contract(contract_payload(), roles)
    execution = plan_execution(contract)
    outcomes = tuple(
        WorkerOutcome(
            task_id=task_id,
            workflow_state="ready_for_owner_review",
            validation_status="passed",
            changed_files=(f"docs/{task_id}.md",),
        )
        for task_id in ("TASK-A", "TASK-B", "TASK-C")
    )
    integration = build_integration_plan(contract, execution, outcomes)
    assert integration.recommended_integration_order == (
        "TASK-A",
        "TASK-B",
        "TASK-C",
    )
    assert integration.conflict_risk == "owner_review_required"
    assert not integration.blocking_findings
    assert "all" in integration.required_revalidation


def test_integration_plan_blocks_unapproved_and_conflicting_worker_output(
    roles: dict[str, AgentRole],
) -> None:
    contract = parse_lia_contract(contract_payload(), roles)
    execution = plan_execution(contract)
    outcomes = (
        WorkerOutcome(
            task_id="TASK-A",
            workflow_state="ready_for_owner_review",
            validation_status="passed",
            changed_files=("docs/shared.md",),
        ),
        WorkerOutcome(
            task_id="TASK-B",
            workflow_state="ready_for_owner_review",
            validation_status="passed",
            changed_files=("docs/shared.md",),
        ),
    )
    integration = build_integration_plan(contract, execution, outcomes)
    assert integration.conflict_risk == "blocked"
    assert any(
        "outside approved boundary" in item for item in integration.blocking_findings
    )
    assert any(
        "worker output conflict" in item for item in integration.blocking_findings
    )


def test_supervisory_report_is_redacted_and_records_no_actions(
    tmp_path: Path, roles: dict[str, AgentRole]
) -> None:
    contract = parse_lia_contract(contract_payload(), roles)
    execution = plan_execution(contract)
    report = LiaSupervisoryReport(
        schema_version=LIA_REPORT_VERSION,
        supervisory_run_id="LIA-TEST",
        parent_milestone="token=private-value",
        generated_at="2026-07-23T12:00:00+00:00",
        branch="customer-management-v1",
        starting_head=HEAD,
        ending_head=HEAD,
        workflow_state="approved",
        workers=(
            SupervisoryWorkerReport(
                task_id="TASK-A",
                agent_id="atlas-one",
                role_id="atlas",
                workflow_state="approved",
                eligibility="parallel_safe",
                dependencies=(),
                validation_status="not_run_dry_run",
                changed_file_boundary=("docs/TASK-A.md",),
                escalation_flags=(),
            ),
        ),
        execution_waves=(("TASK-A", "TASK-B"), ("TASK-C",)),
        dependency_status=(("TASK-A", ()),),
        validation_summary="not executed",
        conflicts=(),
        blockers=(),
        architecture_escalations=(),
        security_escalations=(),
        integration_recommendation=planned_integration(execution, ("all",)),
        owner_decisions_required=("Review.",),
        actions=RunActionAudit(),
        dry_run=True,
    )
    json_path, markdown_path = write_supervisory_report(report, tmp_path)
    assert "private-value" not in json_path.read_text()
    markdown = markdown_path.read_text()
    assert "# LIA Supervisory Report" in markdown
    assert "Commit occurred: False" in markdown
    assert "private-value" not in render_supervisory_markdown(report)


@pytest.mark.parametrize(
    "action",
    [
        Action.CODE_CHANGE,
        Action.STAGE_AND_COMMIT,
        Action.PUSH,
        Action.MERGE,
        Action.DEPLOYMENT,
        Action.DESTRUCTIVE,
    ],
)
def test_lia_never_executes_privileged_actions(tmp_path: Path, action: Action) -> None:
    supervisor = LiaSupervisor.__new__(LiaSupervisor)
    supervisor.repo_root = tmp_path
    supervisor.roles = {}
    with pytest.raises(WorkflowError, match="cannot execute privileged action"):
        supervisor.check_action(action)


def test_repository_divergence_and_staged_index_block_supervision(
    roles: dict[str, AgentRole],
) -> None:
    from development_factory.models import ClassifiedFile

    contract = parse_lia_contract(contract_payload(), roles)
    state = RepositoryState(
        branch="wrong",
        head="b" * 40,
        files=[
            ClassifiedFile(
                path="docs/staged.md",
                state="M ",
                category="documentation",
                staged=True,
                untracked=False,
            )
        ],
    )
    issues = LiaSupervisor._repository_issues(contract, state)
    assert any("branch mismatch" in issue for issue in issues)
    assert any("HEAD mismatch" in issue for issue in issues)
    assert "Git index must be empty" in issues
