from __future__ import annotations

from pathlib import Path

from development_factory.lia_contract import (
    LiaSupervisoryContract,
    load_lia_contract,
)
from development_factory.lia_planner import ExecutionPlan, plan_execution
from development_factory.lia_reports import (
    LIA_REPORT_VERSION,
    LiaSupervisoryReport,
    SupervisoryWorkerReport,
    planned_integration,
    write_supervisory_report,
)
from development_factory.lia_roles import load_agent_roles
from development_factory.models import RepositoryState
from development_factory.repository import inspect_repository
from development_factory.run_records import RunActionAudit, timestamp
from development_factory.workflow import Action, WorkflowError


class LiaSupervisor:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.roles = load_agent_roles(
            self.repo_root / "development-factory" / "agent-roles.json"
        )

    def inspect(
        self, contract_path: Path
    ) -> tuple[LiaSupervisoryContract, ExecutionPlan, tuple[str, ...]]:
        contract = load_lia_contract(self._resolve(contract_path), self.roles)
        plan = plan_execution(contract)
        state = inspect_repository(self.repo_root)
        return contract, plan, self._repository_issues(contract, state)

    def dry_run(self, contract_path: Path) -> tuple[LiaSupervisoryReport, Path, Path]:
        contract, plan, repository_issues = self.inspect(contract_path)
        state = inspect_repository(self.repo_root)
        escalations = tuple(
            f"{worker.task.task_id}: {flag}"
            for worker in contract.workers
            for flag in worker.escalation_flags
        )
        blockers = tuple((*repository_issues, *escalations))
        planned_by_task = {worker.task_id: worker for worker in plan.workers}
        report = LiaSupervisoryReport(
            schema_version=LIA_REPORT_VERSION,
            supervisory_run_id=contract.supervisory_run_id,
            parent_milestone=contract.parent_milestone,
            generated_at=timestamp(),
            branch=state.branch,
            starting_head=contract.expected_starting_head,
            ending_head=state.head,
            workflow_state="blocked" if blockers else "approved",
            workers=tuple(
                SupervisoryWorkerReport(
                    task_id=worker.task.task_id,
                    agent_id=worker.agent_id,
                    role_id=worker.role_id,
                    workflow_state=worker.task.workflow_state.value,
                    eligibility=planned_by_task[worker.task.task_id].eligibility,
                    dependencies=worker.depends_on,
                    validation_status="not_run_dry_run",
                    changed_file_boundary=worker.exclusive_file_boundaries,
                    escalation_flags=worker.escalation_flags,
                )
                for worker in sorted(
                    contract.workers, key=lambda item: item.task.task_id
                )
            ),
            execution_waves=tuple(wave.task_ids for wave in plan.waves),
            dependency_status=tuple(
                (worker.task.task_id, worker.depends_on)
                for worker in sorted(
                    contract.workers, key=lambda item: item.task.task_id
                )
            ),
            validation_summary="not executed; coordination dry run only",
            conflicts=(),
            blockers=blockers,
            architecture_escalations=tuple(
                item for item in escalations if "architecture" in item.lower()
            ),
            security_escalations=tuple(
                item
                for item in escalations
                if any(
                    token in item.lower()
                    for token in ("security", "authorization", "tenant")
                )
            ),
            integration_recommendation=planned_integration(
                plan, contract.validation_requirements
            ),
            owner_decisions_required=(
                "Approve or reject the proposed worker decomposition.",
                "Approve or reject the execution waves.",
                "Grant commit, push, merge, and deployment approvals separately.",
            ),
            actions=RunActionAudit(),
            dry_run=True,
        )
        output = self.repo_root / ".development-factory" / "lia"
        json_path, markdown_path = write_supervisory_report(report, output)
        return report, json_path, markdown_path

    def check_action(self, action: Action) -> None:
        if action not in {Action.INSPECTION, Action.VALIDATION}:
            raise WorkflowError(f"LIA cannot execute privileged action {action.value}")

    @staticmethod
    def _repository_issues(
        contract: LiaSupervisoryContract, state: RepositoryState
    ) -> tuple[str, ...]:
        issues: list[str] = []
        repository = state
        if contract.stop_conditions.stop_on_repository_divergence:
            if repository.branch != contract.expected_branch:
                issues.append(
                    f"branch mismatch: expected {contract.expected_branch}, "
                    f"found {repository.branch}"
                )
            if repository.head != contract.expected_starting_head:
                issues.append(
                    f"HEAD mismatch: expected {contract.expected_starting_head}, "
                    f"found {repository.head}"
                )
        if contract.stop_conditions.require_empty_index and not repository.index_clean:
            issues.append("Git index must be empty")
        return tuple(issues)

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.repo_root / path
