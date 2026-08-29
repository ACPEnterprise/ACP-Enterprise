from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.customer_migration.cutover_plan import (
    CUTOVER_PLAN_VERSION,
    CutoverCheckpoint,
    CutoverPlanCompiler,
    CutoverPlanVersion,
    CutoverPrecondition,
    CutoverRecoveryInstruction,
    CutoverRollbackRequirement,
    CutoverStep,
    CutoverStepDependency,
)
from app.customer_migration.cutover_readiness import CutoverReadiness

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)
USER = UUID(int=3)
READINESS = UUID(int=4)
CREATED = datetime(2026, 8, 5, tzinfo=timezone.utc)


def readiness(*, ready: bool = True) -> CutoverReadiness:
    return CutoverReadiness(
        READINESS,
        "a" * 64,
        ready,
        "ready_for_owner_review" if ready else "not_ready",
        ("source5",),
        () if ready else ("source5",),
        () if ready else ("prerequisite:source5:missing",),
        (),
        (),
        10000 if ready else 0,
        10000 if ready else 0,
        "b" * 64,
    )


def compiler_inputs() -> dict[str, object]:
    step_codes = (
        "source_freeze",
        "artifact_verify",
        "dry_rehearsal",
        "final_eligibility",
    )
    steps = tuple(
        CutoverStep(
            code,
            code,
            code == "dry_rehearsal",
            code == "dry_rehearsal",
            False,
            READINESS,
        )
        for code in step_codes
    )
    dependencies = tuple(
        CutoverStepDependency(step_codes[index], step_codes[index - 1], COMPANY, BRANCH)
        for index in range(1, len(step_codes))
    )
    checkpoints = (
        CutoverCheckpoint(
            "readiness_review", "source_freeze", ("migration.readiness.approve",)
        ),
        CutoverCheckpoint(
            "exception_disposition_review",
            "artifact_verify",
            ("migration.disposition.approve",),
        ),
        CutoverCheckpoint(
            "pilot_boundary_approval", "dry_rehearsal", ("migration.pilot.approve",)
        ),
        CutoverCheckpoint(
            "rollback_approval", "dry_rehearsal", ("migration.rollback.approve",)
        ),
        CutoverCheckpoint(
            "final_cutover_authorization",
            "final_eligibility",
            ("migration.cutover.approve",),
        ),
    )
    return {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "source_provider": "provider-a",
        "source_environment": "restricted-export",
        "readiness": readiness(),
        "transformation_contract_versions": ("customer/v1", "location/v1"),
        "migration_schema_lineage": ("d9f5b1c7e240",),
        "owner_disposition_summary": (("unresolved", 0),),
        "reconciliation_summary": (("blocked", 0),),
        "created_by_user_id": USER,
        "created_at": CREATED,
        "version": CutoverPlanVersion(CUTOVER_PLAN_VERSION, 1),
        "steps": steps,
        "dependencies": dependencies,
        "checkpoints": checkpoints,
        "preconditions": (
            CutoverPrecondition("artifact", "artifact_verify", True, "c" * 64),
        ),
        "rollback_requirements": (
            CutoverRollbackRequirement(
                "dry_run_rollback",
                "dry_rehearsal",
                "verified_backup",
                "restore_database",
                ("backup_available",),
                3600,
                "migration_owner",
                "restore rehearsal passes",
                "d" * 64,
            ),
        ),
        "recovery_instructions": (
            CutoverRecoveryInstruction(
                "obtain_owner_approval",
                "owner_checkpoint_not_approved",
                "Obtain the named owner capability approval.",
                "owner",
                "Approval evidence digest validates.",
            ),
            CutoverRecoveryInstruction(
                "satisfy_precondition",
                "missing_precondition_evidence",
                "Supply matching immutable prerequisite evidence.",
                "migration_owner",
                "Evidence digest matches the plan.",
            ),
            CutoverRecoveryInstruction(
                "resolve_readiness",
                "prerequisite:source5:missing",
                "Resolve the immutable readiness prerequisite.",
                "migration_owner",
                "A new approved readiness assessment validates.",
            ),
            *tuple(
                CutoverRecoveryInstruction(
                    f"recover_{failure}",
                    failure,
                    f"Correct {failure} and regenerate immutable evidence.",
                    "migration_owner",
                    "Corrected evidence validates.",
                )
                for failure in (
                    "missing_source_artifact",
                    "artifact_checksum_mismatch",
                    "missing_transformation_contract",
                    "unresolved_owner_disposition",
                    "unresolved_reconciliation",
                    "missing_scope",
                    "missing_database_backup",
                    "missing_rollback_target",
                    "dependency_failure",
                    "stale_readiness_evidence",
                    "conflicting_plan_version",
                    "interrupted_rehearsal",
                    "duplicate_replay",
                    "cross_company_evidence",
                    "conflicting_approval_evidence",
                    "live_execution_prohibited",
                )
            ),
        ),
    }


def compile_plan(**changes: object):
    values = compiler_inputs()
    values.update(changes)
    return CutoverPlanCompiler().compile(**values)  # type: ignore[arg-type]


def test_compiler_is_deterministic_uuidv5_and_canonical_ordered() -> None:
    first = compile_plan()
    second = compile_plan()
    assert first == second
    assert first.plan_id.version == 5
    assert tuple(step.code for step in first.ordered_steps) == (
        "source_freeze",
        "artifact_verify",
        "dry_rehearsal",
        "final_eligibility",
    )
    assert all(
        step.step_id and step.step_id.version == 5 for step in first.ordered_steps
    )


def test_dependency_cycle_missing_dependency_and_multiple_terminal_fail_closed() -> (
    None
):
    values = compiler_inputs()
    with pytest.raises(ValueError, match="cycle"):
        compile_plan(
            dependencies=(
                CutoverStepDependency(
                    "source_freeze", "artifact_verify", COMPANY, BRANCH
                ),
                CutoverStepDependency(
                    "artifact_verify", "source_freeze", COMPANY, BRANCH
                ),
                *values["dependencies"][1:],  # type: ignore[index]
            )
        )
    with pytest.raises(ValueError, match="missing dependency"):
        compile_plan(
            dependencies=(
                CutoverStepDependency("missing", "source_freeze", COMPANY, BRANCH),
            )
        )
    with pytest.raises(ValueError, match="exactly one terminal"):
        compile_plan(dependencies=())


def test_cross_scope_and_incompatible_readiness_fail_closed() -> None:
    values = compiler_inputs()
    dependencies = values["dependencies"]
    assert isinstance(dependencies, tuple)
    with pytest.raises(ValueError, match="cross-Company"):
        compile_plan(
            dependencies=(
                replace(dependencies[0], company_id=UUID(int=9)),
                *dependencies[1:],
            )
        )
    steps = values["steps"]
    assert isinstance(steps, tuple)
    with pytest.raises(ValueError, match="incompatible readiness"):
        compile_plan(
            steps=(replace(steps[0], readiness_evidence_id=UUID(int=10)), *steps[1:])
        )


def test_executable_and_reversible_steps_require_rollback_evidence() -> None:
    with pytest.raises(ValueError, match="lacks rollback"):
        compile_plan(rollback_requirements=())
    values = compiler_inputs()
    rollback = values["rollback_requirements"]
    assert isinstance(rollback, tuple)
    with pytest.raises(ValueError, match="adequate rollback evidence"):
        compile_plan(
            rollback_requirements=(replace(rollback[0], evidence_digest=None),)
        )


def test_required_checkpoints_and_final_gate_cannot_be_bypassed() -> None:
    values = compiler_inputs()
    checkpoints = values["checkpoints"]
    assert isinstance(checkpoints, tuple)
    with pytest.raises(ValueError, match="checkpoints are missing"):
        compile_plan(checkpoints=checkpoints[:-1])
    with pytest.raises(ValueError, match="can be bypassed"):
        compile_plan(
            checkpoints=tuple(
                replace(item, before_step_code="dry_rehearsal")
                if item.code == "final_cutover_authorization"
                else item
                for item in checkpoints
            )
        )


def test_plan_is_blocked_until_explicit_owner_approvals_exist() -> None:
    plan = compile_plan()
    assert plan.assessment.eligible is False
    assert "migration.cutover.approve" in plan.assessment.required_approvals
    assert any(
        item.code == "checkpoint:final_cutover_authorization"
        for item in plan.assessment.blocking_conditions
    )
