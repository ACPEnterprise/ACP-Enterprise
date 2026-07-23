from __future__ import annotations

import fnmatch
from pathlib import Path

from development_factory.engine import DevelopmentFactory
from development_factory.models import RepositoryState
from development_factory.repository import inspect_repository
from development_factory.run_records import (
    RUN_RECORD_VERSION,
    RunActionAudit,
    RunRecord,
    make_run_id,
    state_snapshot,
    timestamp,
    write_run_record,
)
from development_factory.task_contract import TaskContract, load_task_contract
from development_factory.workflow import (
    Action,
    WorkflowState,
    ensure_action_allowed,
    transition,
)


class TaskRunner:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def inspect(self, contract_path: Path) -> tuple[TaskContract, tuple[str, ...]]:
        contract = load_task_contract(self._resolve(contract_path))
        state = inspect_repository(self.repo_root)
        return contract, self._precondition_issues(contract, state)

    def check_action(
        self,
        contract_path: Path,
        action: Action,
        state: WorkflowState,
    ) -> None:
        contract = load_task_contract(self._resolve(contract_path))
        ensure_action_allowed(action, state, contract.permissions)

    def run(
        self, contract_path: Path, *, dry_run: bool
    ) -> tuple[RunRecord, Path, Path]:
        contract = load_task_contract(self._resolve(contract_path))
        started_at = timestamp()
        starting = inspect_repository(self.repo_root)
        blockers = list(self._precondition_issues(contract, starting))
        commands = ["repository.inspect"]
        validation_result = "not executed (dry run)"
        final_state = contract.workflow_state

        if contract.workflow_state != WorkflowState.APPROVED:
            blockers.append("task must be in approved state before execution")
        if not dry_run and not blockers:
            final_state = transition(
                contract.workflow_state,
                WorkflowState.RUNNING,
                contract.permissions,
            )
            selected, changed_only = self._validation_selection(contract)
            commands.append(
                "development-factory.validate:"
                + ("changed" if changed_only else ",".join(selected))
            )
            report, _, _ = DevelopmentFactory(self.repo_root).validate(
                selected, changed_only=changed_only
            )
            validation_result = str(report["readiness"])
            target = (
                WorkflowState.READY_FOR_OWNER_REVIEW
                if report["exit_status"] == 0
                else WorkflowState.BLOCKED
            )
            final_state = transition(final_state, target, contract.permissions)
            blockers.extend(str(item) for item in report["blocking_failures"])

        ending = inspect_repository(self.repo_root)
        boundary_issues = self._boundary_issues(contract, ending)
        if boundary_issues:
            blockers.extend(boundary_issues)
            if not dry_run and final_state == WorkflowState.RUNNING:
                final_state = WorkflowState.BLOCKED
        if blockers and not dry_run and final_state == WorkflowState.RUNNING:
            final_state = WorkflowState.BLOCKED

        recommended = self._recommendation(dry_run, final_state, blockers)
        record = RunRecord(
            schema_version=RUN_RECORD_VERSION,
            run_id=make_run_id(contract.task_id, started_at),
            task_id=contract.task_id,
            milestone=contract.milestone,
            started_at=started_at,
            completed_at=timestamp(),
            starting_branch=starting.branch,
            starting_head=starting.head,
            ending_branch=ending.branch,
            ending_head=ending.head,
            working_tree_clean_at_start=starting.working_tree_clean,
            working_tree_clean_at_end=ending.working_tree_clean,
            index_clean_at_start=starting.index_clean,
            index_clean_at_end=ending.index_clean,
            commands_executed=tuple(commands),
            validation_result=validation_result,
            changed_files=state_snapshot(ending),
            workflow_state=(
                WorkflowState.BLOCKED if blockers and not dry_run else final_state
            ),
            blockers=tuple(dict.fromkeys(blockers)),
            recommended_next_action=recommended,
            actions=RunActionAudit(),
            dry_run=dry_run,
        )
        output = self.repo_root / ".development-factory" / "runs"
        json_path, markdown_path = write_run_record(record, output)
        return record, json_path, markdown_path

    def _precondition_issues(
        self, contract: TaskContract, state: RepositoryState
    ) -> tuple[str, ...]:
        repository = state
        issues: list[str] = []
        if (
            contract.stop_conditions.stop_on_branch_mismatch
            and repository.branch != contract.expected_branch
        ):
            issues.append(
                f"branch mismatch: expected {contract.expected_branch}, "
                f"found {repository.branch}"
            )
        if (
            contract.stop_conditions.stop_on_head_mismatch
            and repository.head != contract.expected_starting_head
        ):
            issues.append(
                f"HEAD mismatch: expected {contract.expected_starting_head}, "
                f"found {repository.head}"
            )
        if (
            contract.stop_conditions.require_clean_start
            and not repository.working_tree_clean
        ):
            issues.append("working tree must be clean at task start")
        if contract.stop_conditions.require_empty_index and not repository.index_clean:
            issues.append("Git index must be empty at task start")
        return tuple(issues)

    def _boundary_issues(
        self, contract: TaskContract, state: RepositoryState
    ) -> tuple[str, ...]:
        if (
            not contract.stop_conditions.stop_on_unapproved_files
            or not contract.allowed_file_boundaries
        ):
            return ()
        unexpected = [
            item.path
            for item in state.files
            if not any(
                fnmatch.fnmatchcase(item.path, pattern)
                for pattern in contract.allowed_file_boundaries
            )
        ]
        return tuple(f"unapproved changed file: {path}" for path in sorted(unexpected))

    @staticmethod
    def _validation_selection(
        contract: TaskContract,
    ) -> tuple[tuple[str, ...], bool]:
        if contract.required_validation == ("changed",):
            return (), True
        return contract.required_validation, False

    @staticmethod
    def _recommendation(
        dry_run: bool,
        state: WorkflowState,
        blockers: list[str],
    ) -> str:
        if blockers:
            return "Resolve blockers or ask the owner to revise or reject the task."
        if dry_run:
            return (
                "Owner may authorize normal task execution after reviewing the dry run."
            )
        if state == WorkflowState.READY_FOR_OWNER_REVIEW:
            return (
                "Owner review is required; validation does not grant commit approval."
            )
        return "Await explicit owner direction."

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.repo_root / path
