from datetime import datetime, timezone
from inspect import signature
from uuid import UUID

import pytest

from app.customer_migration.cutover_rehearsal import (
    CutoverRehearsalEvidence,
    CutoverRehearsalService,
)
from tests.customer_migration.test_cutover_plan import compile_plan, readiness

CREATED = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
USER = UUID(int=20)


def complete_evidence(**changes: object) -> CutoverRehearsalEvidence:
    approvals = (
        ("migration.readiness.approve", ("1" * 64,)),
        ("migration.disposition.approve", ("2" * 64,)),
        ("migration.pilot.approve", ("3" * 64,)),
        ("migration.rollback.approve", ("4" * 64,)),
        ("migration.cutover.approve", ("5" * 64,)),
    )
    values: dict[str, object] = {
        "precondition_evidence": (("artifact", "c" * 64),),
        "approval_evidence": approvals,
    }
    values.update(changes)
    return CutoverRehearsalEvidence(**values)  # type: ignore[arg-type]


def rehearse(evidence: CutoverRehearsalEvidence):
    return CutoverRehearsalService().rehearse(
        plan=compile_plan(),
        evidence=evidence,
        created_by_user_id=USER,
        created_at=CREATED,
    )


def test_rehearsal_is_deterministic_and_has_no_mutation_ports() -> None:
    first = rehearse(complete_evidence())
    second = rehearse(complete_evidence())
    assert first == second
    assert first.rehearsal_id.version == 5
    assert first.status == "simulated_success"
    assert {item.outcome for item in first.step_results} == {"simulated_success"}
    assert tuple(signature(CutoverRehearsalService).parameters) == ()


@pytest.mark.parametrize(
    "failure",
    (
        "missing_source_artifact",
        "artifact_checksum_mismatch",
        "missing_transformation_contract",
        "unresolved_owner_disposition",
        "unresolved_reconciliation",
        "missing_scope",
        "missing_database_backup",
        "missing_rollback_target",
        "conflicting_plan_version",
        "duplicate_replay",
        "cross_company_evidence",
    ),
)
def test_failure_injection_blocks_exact_step_and_skips_downstream(failure: str) -> None:
    result = rehearse(
        complete_evidence(injected_failures=(("artifact_verify", failure),))
    )
    failed = next(
        item for item in result.step_results if item.step_code == "artifact_verify"
    )
    assert failed.outcome == "blocked"
    assert failed.failure_code == failure
    assert failed.recovery_instruction_code == f"recover_{failure}"
    downstream = result.step_results[result.step_results.index(failed) + 1 :]
    assert all(item.outcome == "skipped" for item in downstream)


def test_missing_and_conflicting_owner_approval_fail_closed() -> None:
    missing = rehearse(complete_evidence(approval_evidence=()))
    assert missing.step_results[0].failure_code == "owner_checkpoint_not_approved"
    approvals = dict(complete_evidence().approval_evidence)
    approvals["migration.readiness.approve"] = ("1" * 64, "9" * 64)
    conflict = rehearse(
        complete_evidence(approval_evidence=tuple(sorted(approvals.items())))
    )
    assert conflict.step_results[0].failure_code == "conflicting_approval_evidence"


def test_stale_readiness_and_interruption_are_deterministic() -> None:
    stale = rehearse(complete_evidence(stale_readiness=True))
    assert stale.step_results[0].failure_code == "stale_readiness_evidence"
    interrupted = rehearse(complete_evidence(interrupted_after_step="artifact_verify"))
    assert interrupted.step_results[2].failure_code == "interrupted_rehearsal"
    assert interrupted.step_results[2].outcome == "skipped"


def test_missing_precondition_evidence_blocks_without_execution() -> None:
    result = rehearse(complete_evidence(precondition_evidence=()))
    artifact = next(
        item for item in result.step_results if item.step_code == "artifact_verify"
    )
    assert artifact.failure_code == "missing_precondition_evidence"
    assert artifact.recovery_instruction_code == "satisfy_precondition"


def test_unready_plan_blocks_at_readiness_gate() -> None:
    plan = compile_plan(readiness=readiness(ready=False))
    result = CutoverRehearsalService().rehearse(
        plan=plan,
        evidence=complete_evidence(),
        created_by_user_id=USER,
        created_at=CREATED,
    )
    assert result.step_results[0].failure_code == "prerequisite:source5:missing"
    assert result.step_results[0].recovery_instruction_code == "resolve_readiness"
