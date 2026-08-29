"""Dry rehearsal of cutover plans with no operational mutation capabilities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from app.customer_migration.cutover_plan import (
    CUTOVER_PLAN_NAMESPACE,
    CutoverCheckpoint,
    CutoverPlan,
    CutoverPrecondition,
)

CUTOVER_REHEARSAL_VERSION = "customer-migration-cutover-rehearsal/v1"


@dataclass(frozen=True)
class CutoverRehearsalStepResult:
    step_id: UUID
    step_code: str
    ordinal: int
    outcome: str
    failure_code: str | None
    recovery_instruction_code: str | None
    evidence_digest: str


@dataclass(frozen=True)
class CutoverRehearsalEvidence:
    precondition_evidence: tuple[tuple[str, str], ...]
    approval_evidence: tuple[tuple[str, tuple[str, ...]], ...]
    injected_failures: tuple[tuple[str, str], ...] = ()
    stale_readiness: bool = False
    interrupted_after_step: str | None = None


@dataclass(frozen=True)
class CutoverRehearsal:
    rehearsal_id: UUID
    plan_id: UUID
    company_id: UUID
    branch_id: UUID
    source_provider: str
    source_environment: str
    transformation_contract_versions: tuple[str, ...]
    migration_schema_lineage: tuple[str, ...]
    readiness_evidence_id: UUID
    readiness_evidence_digest: str
    owner_disposition_summary: tuple[tuple[str, int], ...]
    reconciliation_summary: tuple[tuple[str, int], ...]
    created_by_user_id: UUID
    created_at: datetime
    version: int
    status: str
    step_results: tuple[CutoverRehearsalStepResult, ...]
    evidence_digest: str


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class CutoverRehearsalService:
    """Simulate evidence gates only; deliberately has no operational ports."""

    def rehearse(
        self,
        *,
        plan: CutoverPlan,
        evidence: CutoverRehearsalEvidence,
        created_by_user_id: UUID,
        created_at: datetime,
        version: int = 1,
    ) -> CutoverRehearsal:
        if version < 1:
            raise ValueError("rehearsal version must be positive")
        preconditions = dict(evidence.precondition_evidence)
        approvals = dict(evidence.approval_evidence)
        failures = dict(evidence.injected_failures)
        if len(preconditions) != len(evidence.precondition_evidence):
            raise ValueError("conflicting precondition evidence")
        if len(failures) != len(evidence.injected_failures):
            raise ValueError("conflicting failure injection")
        checkpoints: dict[str, list[CutoverCheckpoint]] = {}
        for checkpoint in plan.checkpoints:
            checkpoints.setdefault(checkpoint.before_step_code, []).append(checkpoint)
        required_preconditions: dict[str, list[CutoverPrecondition]] = {}
        for precondition in plan.preconditions:
            required_preconditions.setdefault(precondition.step_code, []).append(
                precondition
            )
        recovery_by_failure = {
            item.failure_code: item.code for item in plan.recovery_instructions
        }
        static_blockers: dict[str, tuple[str, str]] = {}
        first_step_code = plan.ordered_steps[0].code
        for blocker in plan.assessment.blocking_conditions:
            if blocker.code.startswith(("checkpoint:", "precondition:")):
                continue
            static_blockers[blocker.step_code or first_step_code] = (
                blocker.code,
                blocker.recovery_instruction_code,
            )
        dependency_map: dict[str, set[str]] = {
            step.code: set() for step in plan.ordered_steps
        }
        for dependency in plan.dependencies:
            dependency_map[dependency.step_code].add(dependency.depends_on_code)
        outcomes: dict[str, str] = {}
        results: list[CutoverRehearsalStepResult] = []
        interrupted = False
        for ordinal, step in enumerate(plan.ordered_steps):
            failure: str | None = None
            outcome = "simulated_success"
            if interrupted:
                outcome = "skipped"
                failure = "interrupted_rehearsal"
            elif any(
                outcomes.get(code) != "simulated_success"
                for code in dependency_map[step.code]
            ):
                outcome = "skipped"
                failure = "dependency_failure"
            elif evidence.stale_readiness:
                outcome = "blocked"
                failure = "stale_readiness_evidence"
            elif step.code in static_blockers:
                outcome = "blocked"
                failure = static_blockers[step.code][0]
            else:
                for checkpoint in checkpoints.get(step.code, []):
                    for capability in checkpoint.required_capabilities:
                        values = tuple(sorted(set(approvals.get(capability, ()))))
                        if not values:
                            failure = "owner_checkpoint_not_approved"
                            break
                        if len(values) > 1:
                            failure = "conflicting_approval_evidence"
                            break
                    if failure:
                        break
                if failure is None:
                    for condition in required_preconditions.get(step.code, []):
                        if (
                            condition.required
                            and preconditions.get(condition.code)
                            != condition.evidence_digest
                        ):
                            failure = failures.get(
                                step.code, "missing_precondition_evidence"
                            )
                            break
                failure = failures.get(step.code, failure)
                if step.production_impacting:
                    failure = "live_execution_prohibited"
                if failure:
                    outcome = "blocked"
            if (
                evidence.interrupted_after_step == step.code
                and outcome == "simulated_success"
            ):
                interrupted = True
            recovery = recovery_by_failure.get(failure) if failure else None
            if failure and step.code in static_blockers:
                recovery = static_blockers[step.code][1]
            result_digest = _digest(
                [
                    CUTOVER_REHEARSAL_VERSION,
                    plan.plan_id,
                    step.step_id,
                    ordinal,
                    outcome,
                    failure,
                    recovery,
                    evidence,
                ]
            )
            assert step.step_id is not None
            results.append(
                CutoverRehearsalStepResult(
                    step.step_id,
                    step.code,
                    ordinal,
                    outcome,
                    failure,
                    recovery,
                    result_digest,
                )
            )
            outcomes[step.code] = outcome
        status = (
            "interrupted"
            if interrupted
            else "simulated_success"
            if all(item.outcome == "simulated_success" for item in results)
            else "blocked"
        )
        canonical = [
            CUTOVER_REHEARSAL_VERSION,
            plan.plan_id,
            plan.plan_digest,
            evidence,
            created_by_user_id,
            created_at.isoformat(),
            version,
            results,
            status,
        ]
        digest = _digest(canonical)
        rehearsal_id = uuid5(CUTOVER_PLAN_NAMESPACE, f"rehearsal:{digest}")
        return CutoverRehearsal(
            rehearsal_id,
            plan.plan_id,
            plan.company_id,
            plan.branch_id,
            plan.source_provider,
            plan.source_environment,
            plan.transformation_contract_versions,
            plan.migration_schema_lineage,
            plan.readiness_evidence_id,
            plan.readiness_evidence_digest,
            plan.owner_disposition_summary,
            plan.reconciliation_summary,
            created_by_user_id,
            created_at,
            version,
            status,
            tuple(results),
            digest,
        )
