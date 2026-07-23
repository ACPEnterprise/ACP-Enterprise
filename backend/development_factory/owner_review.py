from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from development_factory.lia_contract import (
    LiaSupervisoryContract,
    WorkerAssignment,
    load_lia_contract,
)
from development_factory.lia_planner import ExecutionPlan, plan_execution
from development_factory.lia_roles import load_agent_roles
from development_factory.reports import redact
from development_factory.review_conflicts import (
    FileConflict,
    ResourceConflict,
    ValidationSummary,
    consolidate_validation,
    detect_file_conflicts,
    detect_resource_conflicts,
    deterministic_review_order,
    migration_schema_findings,
    security_architecture_findings,
)
from development_factory.review_records import (
    OWNER_REVIEW_VERSION,
    ConsolidatedOwnerReview,
    ConsolidationInput,
    ReviewActionAudit,
    WorkerReview,
    canonical_digest,
    file_digest,
    load_consolidation_input,
    load_owner_decision,
    timestamp,
    write_owner_decision,
    write_owner_review,
)
from development_factory.worker_records import (
    load_worker_record_payload,
    worker_record_digest,
)
from development_factory.workspaces import WorkspaceManager


class OwnerReviewError(ValueError):
    pass


class ConsolidationState(str, Enum):
    PENDING = "pending"
    RECORDS_LOADING = "records_loading"
    PROVENANCE_VERIFYING = "provenance_verifying"
    DEPENDENCIES_ANALYZING = "dependencies_analyzing"
    CONFLICTS_ANALYZING = "conflicts_analyzing"
    VALIDATION_CONSOLIDATING = "validation_consolidating"
    REVIEW_GENERATING = "review_generating"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    OWNER_REVIEW_REQUIRED = "owner_review_required"
    CANCELLED = "cancelled"


CONSOLIDATION_TRANSITIONS: dict[ConsolidationState, frozenset[ConsolidationState]] = {
    ConsolidationState.PENDING: frozenset(
        {ConsolidationState.RECORDS_LOADING, ConsolidationState.CANCELLED}
    ),
    ConsolidationState.RECORDS_LOADING: frozenset(
        {
            ConsolidationState.PROVENANCE_VERIFYING,
            ConsolidationState.BLOCKED,
            ConsolidationState.FAILED,
        }
    ),
    ConsolidationState.PROVENANCE_VERIFYING: frozenset(
        {
            ConsolidationState.DEPENDENCIES_ANALYZING,
            ConsolidationState.BLOCKED,
            ConsolidationState.FAILED,
        }
    ),
    ConsolidationState.DEPENDENCIES_ANALYZING: frozenset(
        {
            ConsolidationState.CONFLICTS_ANALYZING,
            ConsolidationState.BLOCKED,
            ConsolidationState.FAILED,
        }
    ),
    ConsolidationState.CONFLICTS_ANALYZING: frozenset(
        {
            ConsolidationState.VALIDATION_CONSOLIDATING,
            ConsolidationState.BLOCKED,
            ConsolidationState.FAILED,
        }
    ),
    ConsolidationState.VALIDATION_CONSOLIDATING: frozenset(
        {
            ConsolidationState.REVIEW_GENERATING,
            ConsolidationState.BLOCKED,
            ConsolidationState.FAILED,
        }
    ),
    ConsolidationState.REVIEW_GENERATING: frozenset(
        {
            ConsolidationState.COMPLETED,
            ConsolidationState.BLOCKED,
            ConsolidationState.FAILED,
        }
    ),
    ConsolidationState.COMPLETED: frozenset({ConsolidationState.OWNER_REVIEW_REQUIRED}),
    ConsolidationState.BLOCKED: frozenset({ConsolidationState.OWNER_REVIEW_REQUIRED}),
    ConsolidationState.FAILED: frozenset({ConsolidationState.OWNER_REVIEW_REQUIRED}),
    ConsolidationState.OWNER_REVIEW_REQUIRED: frozenset(),
    ConsolidationState.CANCELLED: frozenset(),
}


def transition_consolidation(
    current: ConsolidationState, target: ConsolidationState
) -> ConsolidationState:
    if target not in CONSOLIDATION_TRANSITIONS[current]:
        raise OwnerReviewError(
            f"invalid consolidation transition: {current.value} -> {target.value}"
        )
    return target


@dataclass(frozen=True)
class IngestedRecord:
    path: Path
    payload: dict[str, Any]
    digest: str


class OwnerReviewManager:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.roles = load_agent_roles(
            self.repo_root / "development-factory" / "agent-roles.json"
        )
        self.workspace_manager = WorkspaceManager(self.repo_root)
        self.worker_record_root = (
            self.repo_root / ".development-factory" / "worker-executions"
        )
        self.review_root = self.repo_root / ".development-factory" / "owner-reviews"
        self.decision_root = self.repo_root / ".development-factory" / "owner-decisions"

    def inspect(
        self, contract_path: Path, input_path: Path | None = None
    ) -> tuple[str, ...]:
        contract = self._load_contract(contract_path)
        issues = list(self.workspace_manager.primary_repository_issues(contract))
        if input_path is not None:
            request = load_consolidation_input(self._resolve(input_path))
            issues.extend(self._request_issues(contract_path, contract, request))
            records, record_issues = self._ingest(contract, request)
            issues.extend(record_issues)
            for task_id, record in records.items():
                worker = self._workers(contract)[task_id]
                issues.extend(self._provenance_findings(contract, worker, record))
        return tuple(dict.fromkeys(issues))

    def consolidate(
        self, contract_path: Path, input_path: Path
    ) -> tuple[ConsolidatedOwnerReview, Path, Path]:
        contract = self._load_contract(contract_path)
        request = load_consolidation_input(self._resolve(input_path))
        request_issues = self._request_issues(contract_path, contract, request)
        paths = self._review_paths(request.review_id)
        if any(path.exists() for path in paths):
            status = "finalized" if all(path.exists() for path in paths) else "partial"
            raise OwnerReviewError(
                f"review ID has {status} package state; use a new review ID"
            )
        state = ConsolidationState.PENDING
        history = [state.value]
        state = transition_consolidation(state, ConsolidationState.RECORDS_LOADING)
        history.append(state.value)
        records, record_issues = self._ingest(contract, request)
        workers = self._workers(contract)
        plan = plan_execution(contract)

        state = transition_consolidation(state, ConsolidationState.PROVENANCE_VERIFYING)
        history.append(state.value)
        provenance_by_task: dict[str, tuple[str, ...]] = {}
        for task_id, record in records.items():
            provenance_by_task[task_id] = self._provenance_findings(
                contract, workers[task_id], record
            )

        state = transition_consolidation(
            state, ConsolidationState.DEPENDENCIES_ANALYZING
        )
        history.append(state.value)
        dependency_status = self._dependency_status(
            contract, records, provenance_by_task, request
        )

        state = transition_consolidation(state, ConsolidationState.CONFLICTS_ANALYZING)
        history.append(state.value)
        changed_files = {
            task_id: tuple(record.payload.get("files_changed", ()))
            for task_id, record in records.items()
        }
        file_conflicts = detect_file_conflicts(changed_files, workers)
        resource_conflicts = detect_resource_conflicts(contract.workers)
        migration_findings = migration_schema_findings(changed_files, workers)
        security_findings = security_architecture_findings(
            changed_files,
            workers,
            {task_id: record.payload for task_id, record in records.items()},
        )

        state = transition_consolidation(
            state, ConsolidationState.VALIDATION_CONSOLIDATING
        )
        history.append(state.value)
        validation = {
            task_id: consolidate_validation(
                task_id,
                workers[task_id].task.required_validation,
                record.payload,
            )
            for task_id, record in records.items()
        }
        classifications: dict[str, str] = {}
        rationales: dict[str, tuple[str, ...]] = {}
        for task_id in request.included_worker_task_ids:
            classification, rationale = self._classify(
                task_id,
                records.get(task_id),
                provenance_by_task.get(task_id, ()),
                validation.get(task_id),
                dependency_status,
                file_conflicts,
                resource_conflicts,
                security_findings,
                migration_findings,
            )
            classifications[task_id] = classification
            rationales[task_id] = rationale
        review_order = deterministic_review_order(plan, workers, classifications)
        integration_order = self._integration_order(
            plan, classifications, file_conflicts, resource_conflicts
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    *request_issues,
                    *record_issues,
                    *(
                        finding
                        for findings in provenance_by_task.values()
                        for finding in findings
                    ),
                    *migration_findings,
                    *security_findings,
                    *(
                        f"{item.left_task_id}/{item.right_task_id}: "
                        f"{item.classification}: {item.rationale}"
                        for item in file_conflicts
                        if item.classification
                        in {"prohibited_overlap", "integration_conflict_confirmed"}
                    ),
                    *(
                        f"{item.left_task_id}/{item.right_task_id}: "
                        f"{item.classification}: {item.rationale}"
                        for item in resource_conflicts
                        if item.classification == "prohibited_overlap"
                    ),
                )
            )
        )

        state = transition_consolidation(state, ConsolidationState.REVIEW_GENERATING)
        history.append(state.value)
        terminal = (
            ConsolidationState.BLOCKED
            if blockers
            or any(
                value.startswith("blocked_")
                or value
                in {
                    "failed",
                    "cancelled",
                    "stale",
                    "contradictory_record",
                    "missing_record",
                }
                for value in classifications.values()
            )
            else ConsolidationState.COMPLETED
        )
        state = transition_consolidation(state, terminal)
        history.append(state.value)
        state = transition_consolidation(
            state, ConsolidationState.OWNER_REVIEW_REQUIRED
        )
        history.append(state.value)
        review = ConsolidatedOwnerReview(
            schema_version=OWNER_REVIEW_VERSION,
            review_id=request.review_id,
            supervisory_run_id=contract.supervisory_run_id,
            parent_milestone=contract.parent_milestone,
            parent_objective=contract.objective,
            approved_branch=contract.expected_branch,
            approved_starting_sha=contract.expected_starting_head,
            supervisory_contract_digest=request.supervisory_contract_digest,
            included_worker_records=tuple(
                (task_id, record.digest) for task_id, record in sorted(records.items())
            ),
            excluded_or_missing_workers=tuple(sorted(set(workers) - set(records))),
            execution_waves=tuple(wave.task_ids for wave in plan.waves),
            dependency_status=tuple(sorted(dependency_status.items())),
            worker_reviews=tuple(
                WorkerReview(
                    task_id=task_id,
                    worker_id=workers[task_id].agent_id,
                    execution_id=(
                        records[task_id].payload["execution_id"]
                        if task_id in records
                        else None
                    ),
                    record_digest=(
                        records[task_id].digest if task_id in records else None
                    ),
                    classification=classifications[task_id],
                    rationale=rationales[task_id],
                    workspace_id=workers[task_id].workspace.workspace_id,
                    workspace_path=str(
                        self.workspace_manager.identity(
                            contract, workers[task_id]
                        ).workspace_path
                    ),
                    changed_files=changed_files.get(task_id, ()),
                    provenance_findings=provenance_by_task.get(task_id, ()),
                    validation=validation.get(task_id),
                )
                for task_id in request.included_worker_task_ids
            ),
            workspace_provenance_findings=tuple(
                finding
                for task_id in sorted(provenance_by_task)
                for finding in provenance_by_task[task_id]
            ),
            verified_changed_file_summaries=tuple(sorted(changed_files.items())),
            file_conflicts=file_conflicts,
            resource_conflicts=resource_conflicts,
            migration_schema_findings=migration_findings,
            architecture_security_findings=security_findings,
            validation_summaries=tuple(
                validation[task_id] for task_id in sorted(validation)
            ),
            aggregate_revalidation_requirements=self._aggregate_revalidation(
                contract, changed_files
            ),
            recommended_review_order=review_order,
            advisory_future_integration_order=integration_order,
            rejected_or_noneligible_outputs=tuple(
                task_id
                for task_id, classification in sorted(classifications.items())
                if classification != "verified_ready_for_review"
            ),
            blockers=blockers,
            escalations=tuple(
                finding for finding in (*security_findings, *migration_findings)
            ),
            owner_decisions_required=self._owner_decisions(
                classifications, file_conflicts, resource_conflicts
            ),
            recorded_owner_decisions=(),
            secret_redaction_result="applied",
            action_audit=ReviewActionAudit(),
            state_history=tuple(history),
            created_at=timestamp(),
        )
        json_path, markdown_path = write_owner_review(review, self.review_root)
        return review, json_path, markdown_path

    def list(self, contract_path: Path) -> tuple[str, ...]:
        contract = self._load_contract(contract_path)
        results: list[str] = []
        for path in sorted(self.review_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("supervisory_run_id") == contract.supervisory_run_id:
                results.append(str(payload.get("review_id", path.stem)))
        return tuple(results)

    def show(self, contract_path: Path, review_id: str) -> dict[str, Any]:
        contract = self._load_contract(contract_path)
        path = self.review_root / f"{review_id}.json"
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OwnerReviewError(f"unable to load owner review: {exc}") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("supervisory_run_id") != contract.supervisory_run_id
        ):
            raise OwnerReviewError("owner review does not match supervisory contract")
        return payload

    def view_section(self, contract_path: Path, review_id: str, section: str) -> object:
        payload = self.show(contract_path, review_id)
        keys = {
            "workers": "worker_reviews",
            "conflicts": "file_conflicts",
            "validations": "validation_summaries",
            "decisions": "owner_decisions_required",
        }
        return payload[keys[section]]

    def record_decision(
        self, contract_path: Path, review_id: str, decision_path: Path
    ) -> Path:
        contract = self._load_contract(contract_path)
        review_path = self.review_root / f"{review_id}.json"
        review = self.show(contract_path, review_id)
        decision = load_owner_decision(self._resolve(decision_path))
        if decision.supervisory_run_id != contract.supervisory_run_id:
            raise OwnerReviewError("owner decision supervisory run mismatch")
        if decision.review_id != review_id:
            raise OwnerReviewError("owner decision review ID mismatch")
        if decision.review_digest != file_digest(review_path):
            raise OwnerReviewError("owner decision references stale review evidence")
        if decision.worker_task_id is not None and decision.worker_task_id not in {
            item["task_id"] for item in review["worker_reviews"]
        }:
            raise OwnerReviewError("owner decision references unknown worker")
        return write_owner_decision(decision, self.decision_root / review_id)

    def cancel(self, contract_path: Path, review_id: str) -> Path:
        contract = self._load_contract(contract_path)
        path = self.review_root / f"{review_id}.cancelled.json"
        if path.exists():
            raise OwnerReviewError("review cancellation is already recorded")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "supervisory_run_id": contract.supervisory_run_id,
                    "review_id": review_id,
                    "state": ConsolidationState.CANCELLED.value,
                    "cancelled_at": timestamp(),
                    "worker_outputs_preserved": True,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def _ingest(
        self, contract: LiaSupervisoryContract, request: ConsolidationInput
    ) -> tuple[dict[str, IngestedRecord], tuple[str, ...]]:
        paths = (
            tuple(self._resolve(Path(path)) for path in request.worker_records)
            if request.worker_records
            else tuple(sorted(self.worker_record_root.glob("*.json")))
        )
        workers = self._workers(contract)
        records: dict[str, IngestedRecord] = {}
        execution_ids: set[str] = set()
        issues: list[str] = []
        for path in paths:
            try:
                payload = load_worker_record_payload(path)
            except ValueError as exc:
                issues.append(f"{path}: malformed worker record: {redact(str(exc))}")
                continue
            if payload["supervisory_run_id"] != contract.supervisory_run_id:
                issues.append(f"{path}: supervisory run mismatch")
                continue
            task_id = payload["worker_task_id"]
            if task_id not in request.included_worker_task_ids:
                continue
            if task_id not in workers:
                issues.append(f"{path}: unknown worker task {task_id}")
                continue
            execution_id = payload["execution_id"]
            if execution_id in execution_ids:
                issues.append(f"duplicate execution ID: {execution_id}")
                continue
            execution_ids.add(execution_id)
            if task_id in records:
                issues.append(f"contradictory finalized records for {task_id}")
                continue
            records[task_id] = IngestedRecord(
                path, payload, worker_record_digest(payload)
            )
            if not path.with_suffix(".md").is_file():
                issues.append(f"{path}: finalized worker Markdown record is missing")
        missing = set(request.included_worker_task_ids) - set(records)
        if request.review_policy.require_all_workers:
            issues.extend(
                f"missing worker record: {task_id}" for task_id in sorted(missing)
            )
        return records, tuple(issues)

    def _provenance_findings(
        self,
        contract: LiaSupervisoryContract,
        worker: WorkerAssignment,
        record: IngestedRecord,
    ) -> tuple[str, ...]:
        payload = record.payload
        findings: list[str] = []
        identity = self.workspace_manager.identity(contract, worker)
        expected = {
            "worker_id": worker.agent_id,
            "worker_task_id": worker.task.task_id,
            "role_id": worker.role_id,
            "workspace_id": identity.workspace_id,
            "workspace_path": identity.workspace_path,
            "approved_owner_branch": contract.expected_branch,
            "approved_starting_sha": contract.expected_starting_head,
            "expected_workspace_branch": identity.workspace_branch,
            "actual_starting_branch": identity.workspace_branch,
            "actual_ending_branch": identity.workspace_branch,
            "starting_head": contract.expected_starting_head,
            "ending_head": contract.expected_starting_head,
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                findings.append(f"{worker.task.task_id}: record {field} mismatch")
        try:
            metadata = self.workspace_manager.read_metadata(identity)
        except Exception as exc:
            findings.append(
                f"{worker.task.task_id}: workspace metadata unavailable: "
                f"{redact(str(exc))}"
            )
            return tuple(findings)
        if metadata.identity != identity:
            findings.append(f"{worker.task.task_id}: workspace metadata mismatch")
        workspace = Path(identity.workspace_path)
        if not workspace.exists():
            findings.append(f"{worker.task.task_id}: workspace is missing")
            return tuple(findings)
        branch = _git(workspace, "branch", "--show-current").strip()
        head = _git(workspace, "rev-parse", "HEAD").strip()
        status = _status(workspace)
        if branch != identity.workspace_branch:
            findings.append(f"{worker.task.task_id}: workspace branch drift")
        if head != payload.get("ending_head"):
            findings.append(f"{worker.task.task_id}: workspace HEAD disagreement")
        if status["staged"] != tuple(payload.get("staged_files", ())):
            findings.append(f"{worker.task.task_id}: staged-file disagreement")
        actual_changed = tuple(sorted(set(status["changed"])))
        recorded_changed = tuple(sorted(payload.get("files_changed", ())))
        if actual_changed != recorded_changed:
            findings.append(f"{worker.task.task_id}: changed-file disagreement")
        actual_untracked = tuple(sorted(status["untracked"]))
        recorded_untracked = tuple(sorted(payload.get("untracked_files", ())))
        if actual_untracked != recorded_untracked:
            findings.append(f"{worker.task.task_id}: untracked-file disagreement")
        if payload.get("final_index_clean") is True and status["staged"]:
            findings.append(f"{worker.task.task_id}: index no longer clean")
        completed_at = _parse_time(payload.get("completed_at"))
        if completed_at is None:
            findings.append(f"{worker.task.task_id}: completion timestamp is invalid")
        else:
            for relative_path in actual_changed:
                candidate = workspace / relative_path
                if (
                    candidate.exists()
                    and datetime.fromtimestamp(
                        candidate.lstat().st_mtime, tz=completed_at.tzinfo
                    )
                    > completed_at
                ):
                    findings.append(
                        f"{worker.task.task_id}: workspace changed after "
                        f"record finalization: {relative_path}"
                    )
        return tuple(findings)

    def _request_issues(
        self,
        contract_path: Path,
        contract: LiaSupervisoryContract,
        request: ConsolidationInput,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        expected_digest = canonical_digest(
            json.loads(self._resolve(contract_path).read_text(encoding="utf-8"))
        )
        comparisons = (
            (
                request.supervisory_run_id,
                contract.supervisory_run_id,
                "supervisory run",
            ),
            (request.parent_milestone, contract.parent_milestone, "parent milestone"),
            (request.parent_objective, contract.objective, "parent objective"),
            (request.approved_branch, contract.expected_branch, "approved branch"),
            (
                request.approved_starting_sha,
                contract.expected_starting_head,
                "starting SHA",
            ),
            (
                request.supervisory_contract_digest,
                expected_digest,
                "supervisory contract digest",
            ),
        )
        issues.extend(
            f"consolidation input {label} mismatch"
            for actual, expected, label in comparisons
            if actual != expected
        )
        plan = plan_execution(contract)
        expected_waves = tuple(wave.task_ids for wave in plan.waves)
        if request.required_execution_waves != expected_waves:
            issues.append("consolidation execution waves mismatch")
        unknown = set(request.included_worker_task_ids) - set(self._workers(contract))
        if unknown:
            issues.append("consolidation includes unknown worker tasks")
        workers = self._workers(contract)
        expected_validation = {
            selection
            for task_id in request.included_worker_task_ids
            if task_id in workers
            for selection in workers[task_id].task.required_validation
        }
        if set(request.required_validation_evidence) != expected_validation:
            issues.append(
                "consolidation validation evidence differs from worker contracts"
            )
        if not request.required_dependency_evidence:
            issues.append("consolidation cannot disable dependency evidence")
        if self.workspace_manager.primary_repository_issues(contract):
            issues.extend(self.workspace_manager.primary_repository_issues(contract))
        return tuple(issues)

    @staticmethod
    def _dependency_status(
        contract: LiaSupervisoryContract,
        records: dict[str, IngestedRecord],
        provenance: dict[str, tuple[str, ...]],
        request: ConsolidationInput,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for worker in contract.workers:
            if worker.task.task_id not in request.included_worker_task_ids:
                continue
            blockers: list[str] = []
            current = records.get(worker.task.task_id)
            for dependency in worker.depends_on:
                dependency_record = records.get(dependency)
                if dependency_record is None:
                    blockers.append(f"missing dependency {dependency}")
                elif provenance.get(dependency):
                    blockers.append(f"stale dependency {dependency}")
                elif dependency_record.payload.get("recommended_worker_state") != (
                    "completed"
                ):
                    blockers.append(f"blocked dependency {dependency}")
                elif current is not None and (
                    str(dependency_record.payload.get("completed_at"))
                    > str(current.payload.get("started_at"))
                ):
                    blockers.append(f"execution-wave violation after {dependency}")
            result[worker.task.task_id] = (
                "; ".join(blockers) if blockers else "dependencies_satisfied"
            )
        return result

    @staticmethod
    def _classify(
        task_id: str,
        record: IngestedRecord | None,
        provenance: tuple[str, ...],
        validation: ValidationSummary | None,
        dependencies: dict[str, str],
        file_conflicts: tuple[FileConflict, ...],
        resource_conflicts: tuple[ResourceConflict, ...],
        security_findings: tuple[str, ...],
        migration_findings: tuple[str, ...],
    ) -> tuple[str, tuple[str, ...]]:
        if record is None:
            return "missing_record", ("No finalized worker record was found.",)
        payload = record.payload
        if provenance:
            return "blocked_provenance", provenance
        if payload.get("recommended_worker_state") == "cancelled":
            return "cancelled", ("Worker execution was cancelled.",)
        if payload.get("recommended_worker_state") != "completed":
            if payload.get("contamination_findings"):
                return "blocked_contamination", tuple(payload["contamination_findings"])
            if payload.get("boundary_violations"):
                return "blocked_boundary_violation", tuple(
                    payload["boundary_violations"]
                )
            return "failed", tuple(
                payload.get("blockers", ("Worker did not complete.",))
            )
        dependency = dependencies.get(task_id, "dependency evidence missing")
        if dependency != "dependencies_satisfied":
            return "blocked_dependency", (dependency,)
        if validation is None or validation.missing or validation.failed:
            return "blocked_validation", (
                "Required validation evidence is incomplete.",
            )
        if any(
            getattr(item, "left_task_id", None) == task_id
            or getattr(item, "right_task_id", None) == task_id
            for item in file_conflicts
            if getattr(item, "classification", "") == "prohibited_overlap"
        ):
            return "blocked_boundary_violation", ("Prohibited file overlap exists.",)
        if any(
            getattr(item, "left_task_id", None) == task_id
            or getattr(item, "right_task_id", None) == task_id
            for item in resource_conflicts
            if getattr(item, "classification", "") == "prohibited_overlap"
        ):
            return "blocked_resource_conflict", ("Exclusive resource conflict exists.",)
        task_findings = tuple(
            item
            for item in (*security_findings, *migration_findings)
            if item.startswith(f"{task_id}:")
        )
        if task_findings:
            return "blocked_security", task_findings
        if payload.get("escalations"):
            return "verified_review_required", tuple(payload["escalations"])
        return "verified_ready_for_review", ("Evidence is complete for owner review.",)

    @staticmethod
    def _integration_order(
        plan: ExecutionPlan,
        classifications: dict[str, str],
        file_conflicts: tuple[FileConflict, ...],
        resource_conflicts: tuple[ResourceConflict, ...],
    ) -> tuple[tuple[str, str], ...]:
        blocked = bool(file_conflicts) or any(
            getattr(item, "classification", "") == "prohibited_overlap"
            for item in resource_conflicts
        )
        result: list[tuple[str, str]] = []
        for wave in plan.waves:
            for task_id in wave.task_ids:
                if classifications.get(task_id) != "verified_ready_for_review":
                    recommendation = "not_eligible"
                elif blocked:
                    recommendation = "owner_review_only"
                elif len(wave.task_ids) > 1:
                    recommendation = "independent_integration_candidate"
                else:
                    recommendation = "sequential_integration_candidate"
                result.append((task_id, recommendation))
        result.append(("*aggregate*", "aggregate_revalidation_required"))
        return tuple(result)

    @staticmethod
    def _aggregate_revalidation(
        contract: LiaSupervisoryContract,
        changed_files: dict[str, tuple[str, ...]],
    ) -> tuple[str, ...]:
        requirements = list(contract.validation_requirements)
        paths = tuple(path for values in changed_files.values() for path in values)
        if any("alembic/versions/" in path for path in paths):
            requirements.append("migrations")
        requirements.extend(("architecture", "all"))
        return tuple(dict.fromkeys(requirements))

    @staticmethod
    def _owner_decisions(
        classifications: dict[str, str],
        file_conflicts: tuple[FileConflict, ...],
        resource_conflicts: tuple[ResourceConflict, ...],
    ) -> tuple[str, ...]:
        decisions = [
            f"Accept, reject, remediate, or re-execute worker {task_id} "
            f"({classification})."
            for task_id, classification in sorted(classifications.items())
        ]
        if file_conflicts:
            decisions.append("Choose how conflicting file outputs should be handled.")
        if resource_conflicts:
            decisions.append("Resolve shared or exclusive resource ownership.")
        decisions.extend(
            (
                "Approve or reject future integration planning.",
                "Require aggregate validation after any future integration.",
            )
        )
        return tuple(decisions)

    @staticmethod
    def _workers(
        contract: LiaSupervisoryContract,
    ) -> dict[str, WorkerAssignment]:
        return {worker.task.task_id: worker for worker in contract.workers}

    def _load_contract(self, path: Path) -> LiaSupervisoryContract:
        return load_lia_contract(self._resolve(path), self.roles)

    def _review_paths(self, review_id: str) -> tuple[Path, Path]:
        return (
            self.review_root / f"{review_id}.json",
            self.review_root / f"{review_id}.md",
        )

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.repo_root / path


def _status(repo: Path) -> dict[str, tuple[str, ...]]:
    porcelain = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = tuple(item for item in porcelain.split("\0") if item)
    return {
        "changed": tuple(sorted({item[3:] for item in entries})),
        "untracked": tuple(sorted(item[3:] for item in entries if item[:2] == "??")),
        "staged": tuple(
            sorted(item[3:] for item in entries if item[0] not in {" ", "?"})
        ),
    }


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise OwnerReviewError(
            f"Git inspection failed: {redact(completed.stderr or completed.stdout)}"
        )
    return completed.stdout


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
