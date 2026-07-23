from __future__ import annotations

import fnmatch
import json
import os
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from development_factory.engine import DevelopmentFactory
from development_factory.execution_adapters import (
    ExecutionAdapterError,
    LocalExecutionAdapter,
    OperationResult,
    WorkerOperations,
    load_worker_operations,
)
from development_factory.lia_contract import LiaSupervisoryContract, WorkerAssignment
from development_factory.lia_roles import AgentRole, load_agent_roles
from development_factory.reports import redact
from development_factory.worker_records import (
    WORKER_RECORD_VERSION,
    WorkerActionAudit,
    WorkerExecutionRecord,
    WorkerValidationResult,
    write_worker_record,
)
from development_factory.workspaces import WorkspaceManager


class WorkerExecutionError(ValueError):
    pass


class WorkerState(str, Enum):
    PENDING = "pending"
    WORKSPACE_VERIFYING = "workspace_verifying"
    WORKSPACE_READY = "workspace_ready"
    RUNNING = "running"
    VALIDATION_RUNNING = "validation_running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    OWNER_REVIEW_REQUIRED = "owner_review_required"
    CANCELLED = "cancelled"


WORKER_TRANSITIONS: dict[WorkerState, frozenset[WorkerState]] = {
    WorkerState.PENDING: frozenset(
        {WorkerState.WORKSPACE_VERIFYING, WorkerState.CANCELLED}
    ),
    WorkerState.WORKSPACE_VERIFYING: frozenset(
        {WorkerState.WORKSPACE_READY, WorkerState.BLOCKED, WorkerState.FAILED}
    ),
    WorkerState.WORKSPACE_READY: frozenset(
        {WorkerState.RUNNING, WorkerState.VALIDATION_RUNNING, WorkerState.CANCELLED}
    ),
    WorkerState.RUNNING: frozenset(
        {
            WorkerState.VALIDATION_RUNNING,
            WorkerState.BLOCKED,
            WorkerState.FAILED,
            WorkerState.OWNER_REVIEW_REQUIRED,
            WorkerState.CANCELLED,
        }
    ),
    WorkerState.VALIDATION_RUNNING: frozenset(
        {
            WorkerState.COMPLETED,
            WorkerState.BLOCKED,
            WorkerState.FAILED,
            WorkerState.OWNER_REVIEW_REQUIRED,
            WorkerState.CANCELLED,
        }
    ),
    WorkerState.COMPLETED: frozenset({WorkerState.OWNER_REVIEW_REQUIRED}),
    WorkerState.BLOCKED: frozenset({WorkerState.OWNER_REVIEW_REQUIRED}),
    WorkerState.FAILED: frozenset({WorkerState.OWNER_REVIEW_REQUIRED}),
    WorkerState.OWNER_REVIEW_REQUIRED: frozenset(),
    WorkerState.CANCELLED: frozenset(),
}


def transition_worker(current: WorkerState, target: WorkerState) -> WorkerState:
    if target not in WORKER_TRANSITIONS[current]:
        raise WorkerExecutionError(
            f"invalid worker transition: {current.value} -> {target.value}"
        )
    return target


@dataclass(frozen=True)
class GitSnapshot:
    branch: str
    head: str
    changed_files: tuple[str, ...]
    untracked_files: tuple[str, ...]
    staged_files: tuple[str, ...]
    worktrees: tuple[str, ...]
    branches: tuple[str, ...]
    git_config: tuple[str, ...]
    hooks: tuple[tuple[str, int, int], ...]
    ignored_sensitive_files: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.changed_files and not self.untracked_files

    @property
    def index_clean(self) -> bool:
        return not self.staged_files


class WorkerExecutor:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.workspace_manager = WorkspaceManager(self.repo_root)
        self.roles = load_agent_roles(
            self.repo_root / "development-factory" / "agent-roles.json"
        )
        self.record_root = self.repo_root / ".development-factory" / "worker-executions"

    def inspect(self, contract_path: Path, task_id: str) -> tuple[str, tuple[str, ...]]:
        contract, worker, _ = self._resolve_worker(contract_path, task_id)
        inspection = self.workspace_manager.inspect(
            contract_path, worker.workspace.workspace_id
        )
        issues = list(inspection.issues)
        if inspection.classification != "ready":
            issues.append(f"workspace is not ready: {inspection.classification}")
        issues.extend(self.workspace_manager.primary_repository_issues(contract))
        return inspection.classification, tuple(dict.fromkeys(issues))

    def execute(
        self, contract_path: Path, task_id: str, operations_path: Path
    ) -> tuple[WorkerExecutionRecord, Path, Path]:
        contract, worker, role = self._resolve_worker(contract_path, task_id)
        operations = load_worker_operations(self._resolve(operations_path))
        self._validate_execution_contract(contract, worker, role, operations)
        record_paths = self._record_paths(operations.execution_id)
        if any(path.exists() for path in record_paths):
            status = (
                "finalized"
                if all(path.exists() for path in record_paths)
                else "partial"
            )
            raise WorkerExecutionError(
                f"execution ID has {status} record state; owner review required"
            )

        started_at = _timestamp()
        state = WorkerState.PENDING
        history = [state.value]
        state = transition_worker(state, WorkerState.WORKSPACE_VERIFYING)
        history.append(state.value)
        inspection = self.workspace_manager.inspect(
            contract_path, worker.workspace.workspace_id
        )
        if inspection.classification != "ready":
            raise WorkerExecutionError(
                f"workspace verification failed: {inspection.classification}: "
                + "; ".join(inspection.issues)
            )
        metadata = self.workspace_manager.read_metadata(inspection.identity)
        if metadata.identity != inspection.identity:
            raise WorkerExecutionError("workspace metadata identity mismatch")
        primary_before = _snapshot(self.repo_root)
        if not primary_before.clean or not primary_before.index_clean:
            raise WorkerExecutionError("owner primary tree must remain clean")
        workspace = Path(inspection.identity.workspace_path)
        initial = _snapshot(workspace)
        if not initial.clean or not initial.index_clean:
            raise WorkerExecutionError("workspace must be clean before execution")
        state = transition_worker(state, WorkerState.WORKSPACE_READY)
        history.append(state.value)

        mutation_allowed = self._mutation_allowed(contract, worker, role, operations)
        effective = ["inspection", "validation"]
        if mutation_allowed:
            effective.append("mutation")
        adapter = LocalExecutionAdapter(
            workspace,
            approved_patterns=self._approved_patterns(worker),
            resource_claims=worker.shared_resources,
            mutation_allowed=mutation_allowed,
        )
        performed: list[OperationResult] = []
        denied: list[OperationResult] = []
        blockers: list[str] = []
        started_clock = time.monotonic()
        state = transition_worker(state, WorkerState.RUNNING)
        history.append(state.value)
        for operation in operations.operations:
            if (
                time.monotonic() - started_clock
                > operations.termination_policy.execution_timeout_seconds
            ):
                blockers.append("execution timeout exceeded")
                break
            try:
                result = adapter.execute(operation)
                performed.append(result)
            except (ExecutionAdapterError, OSError, UnicodeError) as exc:
                denied.append(
                    OperationResult(
                        operation.operation_id,
                        operation.operation,
                        "denied",
                        redact(str(exc)),
                    )
                )
                blockers.append(f"{operation.operation_id}: {redact(str(exc))}")
                break

        after_operations = _snapshot(workspace)
        boundary_violations = self._boundary_violations(worker, after_operations)
        contamination = self._contamination(
            workspace,
            initial,
            after_operations,
            primary_before,
            _snapshot(self.repo_root),
        )
        if len(after_operations.changed_files) > (
            operations.termination_policy.maximum_files_changed
        ):
            blockers.append("maximum changed-file count exceeded")
        inspected_files = tuple(
            sorted({path for result in performed for path in result.inspected_files})
        )
        if len(inspected_files) > operations.termination_policy.maximum_files_inspected:
            blockers.append("maximum inspected-file count exceeded")
        blockers.extend(boundary_violations)
        blockers.extend(contamination)

        validation_results: list[WorkerValidationResult] = []
        state = transition_worker(state, WorkerState.VALIDATION_RUNNING)
        history.append(state.value)
        if not blockers:
            validation_results.extend(
                self._validate_workspace(workspace, worker, role, operations)
            )
            blockers.extend(
                f"required validation failed: {item.selection}"
                for item in validation_results
                if item.blocks_completion
            )
        elif operations.validation_selections:
            blockers.append("validation blocked by execution findings")
        if set(worker.task.required_validation) - set(operations.validation_selections):
            blockers.append("required worker validation selection is missing")

        final = _snapshot(workspace)
        final_contamination = self._contamination(
            workspace, initial, final, primary_before, _snapshot(self.repo_root)
        )
        blockers.extend(item for item in final_contamination if item not in blockers)
        recommended = WorkerState.BLOCKED if blockers else WorkerState.COMPLETED
        state = transition_worker(state, recommended)
        history.append(state.value)
        state = transition_worker(state, WorkerState.OWNER_REVIEW_REQUIRED)
        history.append(state.value)
        record = WorkerExecutionRecord(
            schema_version=WORKER_RECORD_VERSION,
            execution_id=operations.execution_id,
            supervisory_run_id=contract.supervisory_run_id,
            parent_milestone=contract.parent_milestone,
            worker_task_id=worker.task.task_id,
            worker_id=worker.agent_id,
            role_id=role.role_id,
            role_display_name=role.display_name,
            workspace_id=worker.workspace.workspace_id,
            workspace_path=str(workspace),
            approved_owner_branch=contract.expected_branch,
            approved_starting_sha=contract.expected_starting_head,
            expected_workspace_branch=inspection.identity.workspace_branch,
            actual_starting_branch=initial.branch,
            actual_ending_branch=final.branch,
            starting_head=initial.head,
            ending_head=final.head,
            initial_workspace_status="clean",
            final_workspace_status="clean" if final.clean else "changed",
            initial_index_clean=initial.index_clean,
            final_index_clean=final.index_clean,
            state_history=tuple(history),
            effective_permissions=tuple(effective),
            requested_operations=operations.operations,
            performed_operations=tuple(performed),
            denied_operations=tuple(denied),
            files_inspected=inspected_files,
            files_changed=final.changed_files,
            untracked_files=final.untracked_files,
            staged_files=final.staged_files,
            boundary_violations=tuple(boundary_violations),
            resource_violations=tuple(
                item for item in blockers if "resource" in item.lower()
            ),
            contamination_findings=tuple(final_contamination),
            validation_results=tuple(validation_results),
            blockers=tuple(dict.fromkeys(blockers)),
            escalations=worker.escalation_flags,
            secret_redaction_result="applied",
            recommended_worker_state=recommended.value,
            owner_review_required=True,
            action_audit=WorkerActionAudit(),
            started_at=started_at,
            completed_at=_timestamp(),
        )
        payload_size = len(json.dumps(record.to_dict(), sort_keys=True).encode("utf-8"))
        if payload_size > operations.termination_policy.maximum_output_record_bytes:
            raise WorkerExecutionError(
                "maximum output-record size exceeded; owner review required"
            )
        json_path, markdown_path = write_worker_record(record, self.record_root)
        return record, json_path, markdown_path

    def validate(
        self, contract_path: Path, task_id: str
    ) -> tuple[WorkerValidationResult, ...]:
        contract, worker, role = self._resolve_worker(contract_path, task_id)
        classification, issues = self.inspect(contract_path, task_id)
        if classification != "ready" or issues:
            raise WorkerExecutionError("workspace is not ready for validation")
        workspace = Path(
            self.workspace_manager.identity(contract, worker).workspace_path
        )
        operations = WorkerOperations(
            schema_version="1.0",
            execution_id="validation-only",
            task_id=worker.task.task_id,
            workspace_id=worker.workspace.workspace_id,
            allowed_action_classes=("validation",),
            operations=(),
            validation_selections=worker.task.required_validation,
            termination_policy=_validation_policy(len(worker.task.required_validation)),
            required_report_fields=("validation_results",),
        )
        return self._validate_workspace(workspace, worker, role, operations)

    def cancel(self, contract_path: Path, task_id: str) -> Path:
        contract, worker, _ = self._resolve_worker(contract_path, task_id)
        identity = self.workspace_manager.identity(contract, worker)
        output = self.record_root / f"{worker.task.task_id}.cancelled.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise WorkerExecutionError("worker cancellation is already recorded")
        output.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "supervisory_run_id": contract.supervisory_run_id,
                    "task_id": worker.task.task_id,
                    "workspace_id": identity.workspace_id,
                    "state": WorkerState.CANCELLED.value,
                    "cancelled_at": _timestamp(),
                    "workspace_changes_preserved": True,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return output

    def latest_record(self, task_id: str) -> Path:
        records = sorted(self.record_root.glob("*.json"), reverse=True)
        for path in records:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("worker_task_id") == task_id:
                return path
        raise WorkerExecutionError(f"no finalized worker record for task {task_id}")

    def show(self, contract_path: Path, task_id: str) -> Path:
        self._resolve_worker(contract_path, task_id)
        return self.latest_record(task_id)

    def diff(self, contract_path: Path, task_id: str) -> str:
        contract, worker, _ = self._resolve_worker(contract_path, task_id)
        workspace = Path(
            self.workspace_manager.identity(contract, worker).workspace_path
        )
        return _git(workspace, "diff", "--no-ext-diff", "--")

    def _resolve_worker(
        self, contract_path: Path, task_id: str
    ) -> tuple[LiaSupervisoryContract, WorkerAssignment, AgentRole]:
        roles = self.roles
        from development_factory.lia_contract import load_lia_contract

        contract = load_lia_contract(self._resolve(contract_path), roles)
        matches = [item for item in contract.workers if item.task.task_id == task_id]
        if len(matches) != 1:
            raise WorkerExecutionError(
                f"task ID must identify exactly one worker: {task_id}"
            )
        worker = matches[0]
        return contract, worker, roles[worker.role_id]

    def _validate_execution_contract(
        self,
        contract: LiaSupervisoryContract,
        worker: WorkerAssignment,
        role: AgentRole,
        operations: WorkerOperations,
    ) -> None:
        if operations.task_id != worker.task.task_id:
            raise WorkerExecutionError("operations task ID mismatch")
        if operations.workspace_id != worker.workspace.workspace_id:
            raise WorkerExecutionError("operations workspace ID mismatch")
        supported_validation = set(contract.validation_requirements)
        if "all" not in supported_validation and "changed" not in supported_validation:
            if not set(operations.validation_selections) <= supported_validation:
                raise WorkerExecutionError("validation exceeds parent selection")
        worker_validation = set(worker.task.required_validation)
        if "all" not in worker_validation and "changed" not in worker_validation:
            if not set(operations.validation_selections) <= worker_validation:
                raise WorkerExecutionError("validation exceeds worker selection")
        role_validation = set(role.default_validation)
        if not set(operations.validation_selections) <= role_validation:
            raise WorkerExecutionError("validation exceeds role capability")
        if any(item.mutates for item in operations.operations):
            self._mutation_allowed(contract, worker, role, operations, raise_error=True)

    @staticmethod
    def _mutation_allowed(
        contract: LiaSupervisoryContract,
        worker: WorkerAssignment,
        role: AgentRole,
        operations: WorkerOperations,
        *,
        raise_error: bool = False,
    ) -> bool:
        allowed = all(
            (
                contract.parent_permissions.code_changes,
                worker.task.permissions.code_changes,
                role.may_propose_code_changes,
                "mutation" in operations.allowed_action_classes,
            )
        )
        if raise_error and not allowed:
            raise WorkerExecutionError("effective permission denies mutation")
        return allowed

    @staticmethod
    def _approved_patterns(worker: WorkerAssignment) -> tuple[str, ...]:
        patterns = tuple(
            dict.fromkeys(
                (
                    *worker.exclusive_file_boundaries,
                    *worker.task.allowed_file_boundaries,
                )
            )
        )
        if not patterns:
            raise WorkerExecutionError("worker has no approved file boundary")
        return patterns

    def _boundary_violations(
        self, worker: WorkerAssignment, snapshot: GitSnapshot
    ) -> tuple[str, ...]:
        patterns = self._approved_patterns(worker)
        return tuple(
            f"changed file outside approved boundary: {path}"
            for path in snapshot.changed_files
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        )

    def _validate_workspace(
        self,
        workspace: Path,
        worker: WorkerAssignment,
        role: AgentRole,
        operations: WorkerOperations,
    ) -> tuple[WorkerValidationResult, ...]:
        results: list[WorkerValidationResult] = []
        for selection in operations.validation_selections:
            if selection not in role.default_validation:
                raise WorkerExecutionError("validation selection is not role-approved")
            started = _timestamp()
            report, _, _ = DevelopmentFactory(workspace).validate(
                () if selection == "changed" else (selection,),
                changed_only=selection == "changed",
            )
            passed = report["exit_status"] == 0
            results.append(
                WorkerValidationResult(
                    selection=selection,
                    started_at=started,
                    completed_at=_timestamp(),
                    result=str(report["readiness"]),
                    exit_classification="passed" if passed else "failed",
                    concise_output="; ".join(
                        f"{item['id']}={item['status']}" for item in report["checks"]
                    )[:4000],
                    required=selection in worker.task.required_validation,
                    blocks_completion=not passed,
                )
            )
        return tuple(results)

    @staticmethod
    def _contamination(
        workspace: Path,
        initial: GitSnapshot,
        final: GitSnapshot,
        primary_initial: GitSnapshot,
        primary_final: GitSnapshot,
    ) -> tuple[str, ...]:
        findings: list[str] = []
        if final.staged_files:
            findings.append("workspace contains staged files")
        if final.head != initial.head:
            findings.append("workspace HEAD moved during execution")
        if final.branch != initial.branch:
            findings.append("workspace branch moved during execution")
        if final.git_config != initial.git_config:
            findings.append("workspace Git configuration changed")
        if final.hooks != initial.hooks:
            findings.append("workspace Git hooks changed")
        new_sensitive = set(final.ignored_sensitive_files) - set(
            initial.ignored_sensitive_files
        )
        findings.extend(
            f"unexpected ignored secret-like file: {path}"
            for path in sorted(new_sensitive)
        )
        if final.worktrees != initial.worktrees:
            findings.append("Git worktree registry changed")
        if final.branches != initial.branches:
            findings.append("Git branch registry changed")
        if primary_final.branch != primary_initial.branch:
            findings.append("owner primary branch changed")
        if primary_final.head != primary_initial.head:
            findings.append("owner primary HEAD changed")
        if primary_final.changed_files != primary_initial.changed_files:
            findings.append("owner primary working tree changed")
        if primary_final.staged_files != primary_initial.staged_files:
            findings.append("owner primary index changed")
        for relative in final.changed_files:
            path = workspace / relative
            if path.is_symlink():
                findings.append(f"changed file is a symlink: {relative}")
                continue
            if path.exists() and not stat.S_ISREG(path.stat().st_mode):
                findings.append(f"changed path is not a regular file: {relative}")
                continue
            lowered = relative.lower()
            if lowered.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key")):
                findings.append(f"prohibited generated or secret-like file: {relative}")
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                if any(
                    token in content.lower()
                    for token in (
                        "-----begin private key-----",
                        "-----begin rsa private key-----",
                        "aws_secret_access_key=",
                    )
                ):
                    findings.append(f"credential-like content detected: {relative}")
        return tuple(findings)

    def _record_paths(self, execution_id: str) -> tuple[Path, Path]:
        return (
            self.record_root / f"{execution_id}.json",
            self.record_root / f"{execution_id}.md",
        )

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.repo_root / path


def _snapshot(repo: Path) -> GitSnapshot:
    branch = _git(repo, "branch", "--show-current").strip()
    head = _git(repo, "rev-parse", "HEAD").strip()
    porcelain = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = tuple(item for item in porcelain.split("\0") if item)
    staged = tuple(sorted(item[3:] for item in entries if item[0] not in {" ", "?"}))
    untracked = tuple(sorted(item[3:] for item in entries if item[:2] == "??"))
    changed = tuple(sorted({item[3:] for item in entries}))
    common = Path(_git(repo, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = (repo / common).resolve()
    hooks_root = common / "hooks"
    hooks = tuple(
        (path.name, path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(hooks_root.glob("*"))
        if path.is_file()
    )
    return GitSnapshot(
        branch=branch,
        head=head,
        changed_files=changed,
        untracked_files=untracked,
        staged_files=staged,
        worktrees=tuple(_git(repo, "worktree", "list", "--porcelain").splitlines()),
        branches=tuple(
            _git(repo, "for-each-ref", "--format=%(refname)", "refs/heads").splitlines()
        ),
        git_config=tuple(_git(repo, "config", "--local", "--list").splitlines()),
        hooks=hooks,
        ignored_sensitive_files=_ignored_sensitive_files(repo),
    )


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise WorkerExecutionError(
            f"Git inspection failed: {redact(completed.stderr or completed.stdout)}"
        )
    return completed.stdout


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ignored_sensitive_files(repo: Path) -> tuple[str, ...]:
    results: list[str] = []
    for root, directories, files in os.walk(repo):
        directories[:] = [
            item for item in directories if item not in {".git", ".development-factory"}
        ]
        root_path = Path(root)
        for name in files:
            lowered = name.lower()
            if (
                lowered.startswith(".env") and not lowered.endswith(".example")
            ) or lowered.endswith((".pem", ".key", ".p12", ".sqlite", ".sqlite3")):
                results.append((root_path / name).relative_to(repo).as_posix())
    return tuple(sorted(results))


def _validation_policy(selection_count: int):
    from development_factory.execution_adapters import TerminationPolicy

    return TerminationPolicy(
        maximum_operations=1,
        maximum_mutations=1,
        maximum_files_inspected=1,
        maximum_files_changed=1,
        maximum_output_record_bytes=1000000,
        maximum_validation_selections=max(1, selection_count),
        execution_timeout_seconds=3600,
    )
