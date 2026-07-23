from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Literal

from development_factory.lia_contract import (
    LiaContractError,
    LiaSupervisoryContract,
    ResourceClaim,
    WorkerAssignment,
)


Eligibility = Literal[
    "parallel_safe", "sequential_required", "blocked", "owner_review_required"
]


@dataclass(frozen=True)
class PlannedWorker:
    task_id: str
    agent_id: str
    eligibility: Eligibility
    reason: str


@dataclass(frozen=True)
class ExecutionWave:
    number: int
    task_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    workers: tuple[PlannedWorker, ...]
    waves: tuple[ExecutionWave, ...]


@dataclass(frozen=True)
class WorkerOutcome:
    task_id: str
    workflow_state: str
    validation_status: str
    changed_files: tuple[str, ...]
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntegrationPlan:
    completion_status: tuple[tuple[str, str], ...]
    validation_status: tuple[tuple[str, str], ...]
    changed_file_summaries: tuple[tuple[str, tuple[str, ...]], ...]
    dependency_order: tuple[str, ...]
    conflict_risk: str
    recommended_review_order: tuple[str, ...]
    recommended_integration_order: tuple[str, ...]
    required_revalidation: tuple[str, ...]
    blocking_findings: tuple[str, ...]
    owner_decisions_required: tuple[str, ...]


def validate_decomposition(contract: LiaSupervisoryContract) -> None:
    workers = contract.workers
    task_ids = {worker.task.task_id for worker in workers}
    workspace_ids = [worker.workspace.workspace_id for worker in workers]
    branch_hints = [worker.workspace.branch_hint for worker in workers]
    if len(workspace_ids) != len(set(workspace_ids)):
        raise LiaContractError("worker workspace IDs must be unique")
    if len(branch_hints) != len(set(branch_hints)):
        raise LiaContractError("worker workspace branch hints must be unique")
    for worker in workers:
        unknown = set(worker.depends_on) - task_ids
        if unknown:
            raise LiaContractError(
                f"worker {worker.task.task_id} has unknown dependencies: "
                f"{', '.join(sorted(unknown))}"
            )
        if worker.task.task_id in worker.depends_on:
            raise LiaContractError(
                f"worker {worker.task.task_id} cannot depend on itself"
            )
    _topological_order(workers)
    for index, left in enumerate(workers):
        for right in workers[index + 1 :]:
            overlap = _file_overlap(left, right)
            if overlap:
                raise LiaContractError(
                    f"exclusive file ownership conflict between "
                    f"{left.task.task_id} and {right.task.task_id}: {overlap}"
                )
            resource = _exclusive_resource_conflict(left, right)
            if resource:
                raise LiaContractError(
                    f"exclusive {resource.resource_type} ownership conflict "
                    f"for {resource.resource_id}"
                )


def plan_execution(contract: LiaSupervisoryContract) -> ExecutionPlan:
    validate_decomposition(contract)
    by_id = {worker.task.task_id: worker for worker in contract.workers}
    completed: set[str] = set()
    remaining = set(by_id)
    waves: list[ExecutionWave] = []
    while remaining:
        ready = sorted(
            task_id
            for task_id in remaining
            if set(by_id[task_id].depends_on) <= completed
        )
        if not ready:
            raise LiaContractError("dependency graph cannot be scheduled")
        wave: list[str] = []
        for task_id in ready:
            worker = by_id[task_id]
            if not contract.parallel_execution_approved and wave:
                continue
            if wave and (
                not worker.parallel_eligible
                or any(not by_id[other_task].parallel_eligible for other_task in wave)
            ):
                continue
            if any(
                _parallel_conflict(worker, by_id[other_task]) for other_task in wave
            ):
                continue
            wave.append(task_id)
        if not wave:
            wave.append(ready[0])
        waves.append(ExecutionWave(number=len(waves) + 1, task_ids=tuple(wave)))
        completed.update(wave)
        remaining.difference_update(wave)

    wave_sizes = {
        task_id: len(wave.task_ids) for wave in waves for task_id in wave.task_ids
    }
    planned: list[PlannedWorker] = []
    for task_id in sorted(by_id):
        worker = by_id[task_id]
        if worker.escalation_flags:
            eligibility: Eligibility = "owner_review_required"
            reason = "explicit escalation: " + ", ".join(worker.escalation_flags)
        elif wave_sizes[task_id] > 1:
            eligibility = "parallel_safe"
            reason = "dependencies and exclusive/shared boundaries permit this wave"
        else:
            eligibility = "sequential_required"
            reason = (
                "dependency, shared resource, worker setting, or parent policy "
                "requires an isolated wave"
            )
        planned.append(
            PlannedWorker(
                task_id=task_id,
                agent_id=worker.agent_id,
                eligibility=eligibility,
                reason=reason,
            )
        )
    return ExecutionPlan(workers=tuple(planned), waves=tuple(waves))


def build_integration_plan(
    contract: LiaSupervisoryContract,
    execution: ExecutionPlan,
    outcomes: tuple[WorkerOutcome, ...],
) -> IntegrationPlan:
    expected = {worker.task.task_id for worker in contract.workers}
    supplied = {outcome.task_id for outcome in outcomes}
    unknown = supplied - expected
    if unknown:
        raise LiaContractError(
            f"integration outcomes contain unknown tasks: {', '.join(sorted(unknown))}"
        )
    by_task = {outcome.task_id: outcome for outcome in outcomes}
    order = tuple(task for wave in execution.waves for task in wave.task_ids)
    blockers = tuple(
        blocker
        for task_id in order
        for blocker in by_task.get(
            task_id,
            WorkerOutcome(task_id, "not_started", "not_run", ()),
        ).blockers
    )
    incomplete = [task_id for task_id in order if task_id not in by_task]
    if incomplete:
        blockers += tuple(
            f"worker outcome missing: {task_id}" for task_id in incomplete
        )
    failed = [
        item.task_id
        for item in outcomes
        if item.validation_status not in {"passed", "ready_for_owner_review"}
    ]
    blockers += tuple(f"worker validation incomplete: {task_id}" for task_id in failed)
    changed_owners: dict[str, str] = {}
    workers_by_task = {worker.task.task_id: worker for worker in contract.workers}
    for outcome in outcomes:
        worker = workers_by_task[outcome.task_id]
        approved_patterns = (
            *worker.exclusive_file_boundaries,
            *worker.task.allowed_file_boundaries,
        )
        for path in outcome.changed_files:
            if not any(
                fnmatch.fnmatchcase(path, pattern) for pattern in approved_patterns
            ):
                blockers += (
                    f"worker output outside approved boundary: "
                    f"{outcome.task_id}: {path}",
                )
            previous = changed_owners.get(path)
            if previous is not None and previous != outcome.task_id:
                blockers += (
                    f"worker output conflict: {previous} and {outcome.task_id}: {path}",
                )
            changed_owners[path] = outcome.task_id
    conflict_risk = "blocked" if blockers else "owner_review_required"
    return IntegrationPlan(
        completion_status=tuple(
            (
                task_id,
                by_task[task_id].workflow_state
                if task_id in by_task
                else "not_started",
            )
            for task_id in order
        ),
        validation_status=tuple(
            (
                task_id,
                by_task[task_id].validation_status if task_id in by_task else "not_run",
            )
            for task_id in order
        ),
        changed_file_summaries=tuple(
            (
                task_id,
                tuple(sorted(by_task[task_id].changed_files))
                if task_id in by_task
                else (),
            )
            for task_id in order
        ),
        dependency_order=order,
        conflict_risk=conflict_risk,
        recommended_review_order=order,
        recommended_integration_order=order,
        required_revalidation=contract.validation_requirements,
        blocking_findings=blockers,
        owner_decisions_required=(
            "Review every worker boundary and validation record.",
            "Approve or reject the proposed integration order.",
            "Grant any later privileged action separately.",
        ),
    )


def _topological_order(workers: tuple[WorkerAssignment, ...]) -> tuple[str, ...]:
    dependencies = {worker.task.task_id: set(worker.depends_on) for worker in workers}
    order: list[str] = []
    ready = sorted(task_id for task_id, values in dependencies.items() if not values)
    while ready:
        task_id = ready.pop(0)
        order.append(task_id)
        for candidate in sorted(dependencies):
            if task_id in dependencies[candidate]:
                dependencies[candidate].remove(task_id)
                if not dependencies[candidate] and candidate not in order:
                    ready.append(candidate)
                    ready.sort()
    if len(order) != len(workers):
        raise LiaContractError("worker dependency graph contains a cycle")
    return tuple(order)


def _file_overlap(left: WorkerAssignment, right: WorkerAssignment) -> str | None:
    for left_pattern in left.exclusive_file_boundaries:
        for right_pattern in right.exclusive_file_boundaries:
            if _patterns_overlap(left_pattern, right_pattern):
                return left_pattern
    return None


def _patterns_overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    if fnmatch.fnmatchcase(left, right) or fnmatch.fnmatchcase(right, left):
        return True
    left_prefix = left.split("*", 1)[0]
    right_prefix = right.split("*", 1)[0]
    return bool(left_prefix and right_prefix) and (
        left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix)
    )


def _exclusive_resource_conflict(
    left: WorkerAssignment, right: WorkerAssignment
) -> ResourceClaim | None:
    for left_claim in left.shared_resources:
        for right_claim in right.shared_resources:
            if (
                left_claim.resource_type == right_claim.resource_type
                and left_claim.resource_id == right_claim.resource_id
                and "exclusive" in {left_claim.mode, right_claim.mode}
            ):
                return left_claim
    return None


def _parallel_conflict(left: WorkerAssignment, right: WorkerAssignment) -> bool:
    for left_claim in left.shared_resources:
        for right_claim in right.shared_resources:
            if (
                left_claim.resource_type == right_claim.resource_type
                and left_claim.resource_id == right_claim.resource_id
            ):
                return True
    return False
