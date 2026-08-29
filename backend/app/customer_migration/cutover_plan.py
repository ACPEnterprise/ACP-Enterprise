"""Provider-neutral deterministic cutover planning contracts; no executor exists."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid5

from app.customer_migration.cutover_readiness import CutoverReadiness

CUTOVER_PLAN_VERSION = "customer-migration-cutover-plan/v2"
CUTOVER_PLAN_NAMESPACE = UUID("6b087ba2-3ef5-5af7-9e74-cba00dc877db")
REQUIRED_CHECKPOINTS = frozenset(
    {
        "readiness_review",
        "exception_disposition_review",
        "pilot_boundary_approval",
        "rollback_approval",
        "final_cutover_authorization",
    }
)


@dataclass(frozen=True)
class CutoverPlanVersion:
    contract_version: str
    version: int
    supersedes_plan_id: UUID | None = None


@dataclass(frozen=True)
class CutoverStep:
    code: str
    category: str
    executable: bool
    reversible: bool
    production_impacting: bool
    readiness_evidence_id: UUID
    step_id: UUID | None = None


@dataclass(frozen=True)
class CutoverStepDependency:
    step_code: str
    depends_on_code: str
    company_id: UUID
    branch_id: UUID


@dataclass(frozen=True)
class CutoverCheckpoint:
    code: str
    before_step_code: str
    required_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class CutoverPrecondition:
    code: str
    step_code: str
    required: bool
    evidence_digest: str | None
    maximum_evidence_age_seconds: int | None = None


@dataclass(frozen=True)
class CutoverBlocker:
    code: str
    step_code: str | None
    recovery_instruction_code: str


@dataclass(frozen=True)
class CutoverRollbackRequirement:
    code: str
    step_code: str
    required_backup_or_artifact: str
    rollback_action_type: str
    recovery_prerequisites: tuple[str, ...]
    maximum_evidence_age_seconds: int
    responsible_authority: str
    verification_requirement: str
    evidence_digest: str | None


@dataclass(frozen=True)
class CutoverRecoveryInstruction:
    code: str
    failure_code: str
    corrective_action: str
    responsible_authority: str
    verification_requirement: str


@dataclass(frozen=True)
class CutoverPlanAssessment:
    eligible: bool
    terminal_step_code: str
    blocking_conditions: tuple[CutoverBlocker, ...]
    required_approvals: tuple[str, ...]


@dataclass(frozen=True)
class CutoverPlan:
    plan_id: UUID
    plan_digest: str
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
    version: CutoverPlanVersion
    ordered_steps: tuple[CutoverStep, ...]
    dependencies: tuple[CutoverStepDependency, ...]
    checkpoints: tuple[CutoverCheckpoint, ...]
    preconditions: tuple[CutoverPrecondition, ...]
    rollback_requirements: tuple[CutoverRollbackRequirement, ...]
    recovery_instructions: tuple[CutoverRecoveryInstruction, ...]
    assessment: CutoverPlanAssessment


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _normalized(value: str, label: str) -> str:
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be normalized")
    return value


def _sha(value: str | None) -> bool:
    return (
        value is not None
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


class CutoverPlanCompiler:
    """Compile canonical plan evidence; it cannot run any step."""

    def compile(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        source_provider: str,
        source_environment: str,
        readiness: CutoverReadiness,
        transformation_contract_versions: tuple[str, ...],
        migration_schema_lineage: tuple[str, ...],
        owner_disposition_summary: tuple[tuple[str, int], ...],
        reconciliation_summary: tuple[tuple[str, int], ...],
        created_by_user_id: UUID,
        created_at: datetime,
        version: CutoverPlanVersion,
        steps: tuple[CutoverStep, ...],
        dependencies: tuple[CutoverStepDependency, ...],
        checkpoints: tuple[CutoverCheckpoint, ...],
        preconditions: tuple[CutoverPrecondition, ...],
        rollback_requirements: tuple[CutoverRollbackRequirement, ...],
        recovery_instructions: tuple[CutoverRecoveryInstruction, ...],
    ) -> CutoverPlan:
        provider = _normalized(source_provider, "source provider").lower()
        environment = _normalized(source_environment, "source environment").lower()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if version.contract_version != CUTOVER_PLAN_VERSION or version.version < 1:
            raise ValueError("cutover plan version is unsupported")
        transforms = tuple(sorted(set(transformation_contract_versions)))
        lineage = tuple(migration_schema_lineage)
        if len(transforms) != len(transformation_contract_versions):
            raise ValueError("duplicate transformation contract versions")
        if not transforms or not lineage:
            raise ValueError(
                "transformation versions and migration lineage are required"
            )
        if any(
            not _normalized(value, "contract or lineage value")
            for value in transforms + lineage
        ):
            raise AssertionError("unreachable")
        by_code = {step.code: step for step in steps}
        if len(by_code) != len(steps):
            raise ValueError("duplicate step identities")
        for step in steps:
            _normalized(step.code, "step code")
            _normalized(step.category, "step category")
            if step.readiness_evidence_id != readiness.readiness_id:
                raise ValueError("step references incompatible readiness evidence")
        dependency_set = set(dependencies)
        if len(dependency_set) != len(dependencies):
            raise ValueError("duplicate dependencies")
        incoming: dict[str, set[str]] = {code: set() for code in by_code}
        outgoing: dict[str, set[str]] = {code: set() for code in by_code}
        for dependency in dependency_set:
            if dependency.company_id != company_id or dependency.branch_id != branch_id:
                raise ValueError("cross-Company or cross-Branch dependency")
            if (
                dependency.step_code not in by_code
                or dependency.depends_on_code not in by_code
            ):
                raise ValueError("missing dependency")
            incoming[dependency.step_code].add(dependency.depends_on_code)
            outgoing[dependency.depends_on_code].add(dependency.step_code)
        terminal = sorted(code for code, values in outgoing.items() if not values)
        if len(terminal) != 1:
            raise ValueError("cutover plan requires exactly one terminal step")
        remaining = {code: set(values) for code, values in incoming.items()}
        ordered_codes: list[str] = []
        while remaining:
            available = sorted(code for code, values in remaining.items() if not values)
            if not available:
                raise ValueError("cutover dependency cycle detected")
            ordered_codes.extend(available)
            for code in available:
                del remaining[code]
            for values in remaining.values():
                values.difference_update(available)
        reachable = {terminal[0]}
        while True:
            prior = set(reachable)
            reachable.update(
                code for code, values in outgoing.items() if values & reachable
            )
            if reachable == prior:
                break
        if reachable != set(by_code):
            raise ValueError("cutover plan contains unreachable steps")
        rollback = tuple(sorted(rollback_requirements, key=lambda item: item.code))
        if any(item.step_code not in by_code for item in rollback):
            raise ValueError("rollback requirement references a missing step")
        rollback_by_step = {item.step_code: item for item in rollback}
        if len(rollback_by_step) != len(rollback):
            raise ValueError("duplicate rollback requirements")
        for step in steps:
            requirement = rollback_by_step.get(step.code)
            if step.executable and requirement is None:
                raise ValueError("execution step lacks rollback requirement")
            if step.reversible and (
                requirement is None or not _sha(requirement.evidence_digest)
            ):
                raise ValueError("reversible step lacks adequate rollback evidence")
        if any(
            item.maximum_evidence_age_seconds <= 0
            or not item.responsible_authority
            or not item.verification_requirement
            for item in rollback
        ):
            raise ValueError("rollback requirement is incomplete")
        checkpoint_values = tuple(sorted(checkpoints, key=lambda item: item.code))
        if len({item.code for item in checkpoint_values}) != len(checkpoint_values):
            raise ValueError("duplicate checkpoint identities")
        checkpoint_codes = {item.code for item in checkpoint_values}
        if not REQUIRED_CHECKPOINTS.issubset(checkpoint_codes):
            raise ValueError("required owner checkpoints are missing")
        final = next(
            item
            for item in checkpoint_values
            if item.code == "final_cutover_authorization"
        )
        if final.before_step_code != terminal[0] or not final.required_capabilities:
            raise ValueError("final owner checkpoint can be bypassed")
        for checkpoint in checkpoint_values:
            if (
                checkpoint.before_step_code not in by_code
                or not checkpoint.required_capabilities
            ):
                raise ValueError("owner checkpoint is invalid")
        precondition_values = tuple(sorted(preconditions, key=lambda item: item.code))
        if len({item.code for item in precondition_values}) != len(precondition_values):
            raise ValueError("duplicate preconditions")
        if any(item.step_code not in by_code for item in precondition_values):
            raise ValueError("precondition references a missing step")
        blockers = [
            CutoverBlocker(code, None, "resolve_readiness")
            for code in readiness.blocking_conditions
        ]
        blockers.extend(
            CutoverBlocker(
                f"precondition:{item.code}", item.step_code, "satisfy_precondition"
            )
            for item in precondition_values
            if item.required and not _sha(item.evidence_digest)
        )
        blockers.extend(
            CutoverBlocker(
                f"checkpoint:{item.code}",
                item.before_step_code,
                "obtain_owner_approval",
            )
            for item in checkpoint_values
        )
        if any(step.production_impacting for step in steps):
            blockers.append(
                CutoverBlocker(
                    "live_execution_prohibited",
                    terminal[0],
                    "future_owner_authorized_milestone",
                )
            )
        recovery = tuple(sorted(recovery_instructions, key=lambda item: item.code))
        recovery_codes = {item.code for item in recovery}
        if any(
            item.recovery_instruction_code not in recovery_codes for item in blockers
        ):
            raise ValueError("blocking condition lacks recovery instruction")
        dependency_values = tuple(
            sorted(
                dependency_set, key=lambda item: (item.step_code, item.depends_on_code)
            )
        )
        canonical_steps = tuple(
            replace(by_code[code], step_id=None) for code in ordered_codes
        )
        canonical = [
            CUTOVER_PLAN_VERSION,
            company_id,
            branch_id,
            provider,
            environment,
            transforms,
            lineage,
            readiness.readiness_id,
            readiness.evidence_digest,
            tuple(sorted(owner_disposition_summary)),
            tuple(sorted(reconciliation_summary)),
            created_by_user_id,
            created_at.isoformat(),
            version,
            canonical_steps,
            dependency_values,
            checkpoint_values,
            precondition_values,
            rollback,
            recovery,
            tuple(sorted(blockers, key=lambda item: (item.code, item.step_code or ""))),
        ]
        plan_digest = _digest(canonical)
        plan_id = uuid5(CUTOVER_PLAN_NAMESPACE, plan_digest)
        ordered_steps = tuple(
            replace(step, step_id=uuid5(plan_id, f"step:{index}:{step.code}"))
            for index, step in enumerate(canonical_steps)
        )
        assessment = CutoverPlanAssessment(
            eligible=not blockers,
            terminal_step_code=terminal[0],
            blocking_conditions=tuple(
                sorted(blockers, key=lambda item: (item.code, item.step_code or ""))
            ),
            required_approvals=tuple(
                sorted(
                    {
                        capability
                        for item in checkpoint_values
                        for capability in item.required_capabilities
                    }
                )
            ),
        )
        return CutoverPlan(
            plan_id,
            plan_digest,
            company_id,
            branch_id,
            provider,
            environment,
            transforms,
            lineage,
            readiness.readiness_id,
            readiness.evidence_digest,
            tuple(sorted(owner_disposition_summary)),
            tuple(sorted(reconciliation_summary)),
            created_by_user_id,
            created_at,
            version,
            ordered_steps,
            dependency_values,
            checkpoint_values,
            precondition_values,
            rollback,
            recovery,
            assessment,
        )
