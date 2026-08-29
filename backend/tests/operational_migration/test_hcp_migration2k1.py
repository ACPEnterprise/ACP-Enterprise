from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2ExecutionPlanBuilder,
)
from app.operational_migration.hcp_migration2k1 import (
    SEQUENCING_CONTRACT_VERSION,
    AppointmentCorrection,
    AppointmentSequenceError,
    RetainedAppointmentProjection,
    SupersedingAppointmentRepairPlan,
    apply_job_sequence_corrections,
    build_appointment_sequence_plan,
    qualify_retained_checkpoint,
)
from app.operational_migration.service import AppointmentMigrationRecord

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
MASTER_ID = UUID("63273602-8619-5c0b-8b49-8537338b04b5")
REPAIR_ID = UUID("5e17975d-0461-5187-b0ea-f1cbe7b58df1")
OLD_DIGEST = "64df671d21ab95818ae6035949202e6d61195733013ff63485471164e9b64d8a"


def appointment(source_id: str, job_id: str, hour: int, *, end_minutes: int = 30):
    start = NOW + timedelta(hours=hour)
    return AppointmentMigrationRecord(
        source_id=source_id,
        source_job_id=job_id,
        source_customer_id="cus_safe",
        source_service_location_id="adr_safe",
        status="scheduled",
        arrival_window_start_at=start,
        arrival_window_end_at=start + timedelta(minutes=end_minutes),
        duration_minutes=end_minutes,
    )


def retained(record: AppointmentMigrationRecord, current: int, ordinal: int):
    return RetainedAppointmentProjection(
        link_id=UUID(int=ordinal),
        job_id=UUID(int=100 + ordinal),
        appointment_id=UUID(int=200 + ordinal),
        source_id=record.source_id,
        current_sequence=current,
    )


def test_sequence_contract_is_chronological_deterministic_and_job_scoped() -> None:
    rows = (
        appointment("appt_c", "job_a", 2),
        appointment("appt_b", "job_a", 1),
        appointment("appt_a", "job_a", 1),
        appointment("appt_d", "job_b", 8),
    )
    plan = build_appointment_sequence_plan(rows)
    reversed_plan = build_appointment_sequence_plan(tuple(reversed(rows)))
    assert plan.sequence_by_source_id() == {
        "appt_a": 1,
        "appt_b": 2,
        "appt_c": 3,
        "appt_d": 1,
    }
    assert reversed_plan.digest == plan.digest
    assert plan.job_count == 2
    assert plan.single_visit_job_count == 1
    assert plan.multi_visit_job_count == 1
    assert plan.multi_visit_appointment_count == 3
    assert plan.visits_beyond_first == 2
    assert plan.maximum_visits == 3


def test_duplicate_source_identity_and_missing_timing_fail_closed() -> None:
    row = appointment("appt_a", "job_a", 1)
    with pytest.raises(AppointmentSequenceError, match="duplicate_appointment"):
        build_appointment_sequence_plan((row, row))
    with pytest.raises(AppointmentSequenceError, match="evidence_incomplete"):
        build_appointment_sequence_plan(
            (
                AppointmentMigrationRecord(
                    source_id="appt_b",
                    source_job_id="job_a",
                    source_customer_id="cus_safe",
                    source_service_location_id="adr_safe",
                    status="scheduled",
                    arrival_window_start_at=None,
                    arrival_window_end_at=NOW,
                    duration_minutes=None,
                ),
            )
        )


def test_checkpoint_preserves_correct_rows_and_qualifies_swaps() -> None:
    first = appointment("appt_a", "job_a", 1)
    second = appointment("appt_b", "job_a", 2)
    third = appointment("appt_c", "job_b", 3)
    plan = build_appointment_sequence_plan((first, second, third))
    checkpoint = qualify_retained_checkpoint(
        plan=plan,
        retained=(retained(first, 2, 1), retained(second, 1, 2), retained(third, 1, 3)),
        accepted_job_count=1094,
    )
    assert checkpoint.retained_count == 3
    assert checkpoint.reused_count == 1
    assert checkpoint.correction_count == 2
    assert checkpoint.remaining_count == 0
    assert {item.corrected_sequence for item in checkpoint.corrections} == {1, 2}


def test_superseding_plan_is_stable_and_preserves_old_digest() -> None:
    rows = (appointment("appt_a", "job_a", 1), appointment("appt_b", "job_a", 2))
    sequence = build_appointment_sequence_plan(rows)
    checkpoint = qualify_retained_checkpoint(
        plan=sequence,
        retained=(retained(rows[0], 2, 1), retained(rows[1], 1, 2)),
        accepted_job_count=1094,
    )
    first = SupersedingAppointmentRepairPlan.build(
        master_id=MASTER_ID,
        repair_id=REPAIR_ID,
        original_repair_plan_digest=OLD_DIGEST,
        sequence_plan=sequence,
        checkpoint=checkpoint,
    )
    again = SupersedingAppointmentRepairPlan.build(
        master_id=MASTER_ID,
        repair_id=REPAIR_ID,
        original_repair_plan_digest=OLD_DIGEST,
        sequence_plan=sequence,
        checkpoint=checkpoint,
    )
    assert first == again
    assert first.generation == 2
    assert first.original_repair_plan_digest == OLD_DIGEST
    assert first.sequencing_contract_version == SEQUENCING_CONTRACT_VERSION
    assert first.digest != OLD_DIGEST


class _ScalarRows:
    def __init__(self, rows: tuple[SimpleNamespace, ...]) -> None:
        self._rows = rows

    def all(self) -> tuple[SimpleNamespace, ...]:
        return self._rows


class _CorrectionSession:
    def __init__(self, rows: tuple[SimpleNamespace, ...]) -> None:
        self.rows = rows
        self.added: list[object] = []
        self.flush_states: list[tuple[int, ...]] = []

    async def scalars(self, _statement: object) -> _ScalarRows:
        return _ScalarRows(self.rows)

    async def scalar(self, _statement: object) -> None:
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        state = tuple(item.visit_sequence for item in self.rows)
        assert len(state) == len(set(state))
        self.flush_states.append(state)


@pytest.mark.asyncio
async def test_atomic_job_swap_uses_noncolliding_transactional_band() -> None:
    company_id, branch_id, job_id = UUID(int=500), UUID(int=501), UUID(int=502)
    rows = (
        SimpleNamespace(
            id=UUID(int=1),
            company_id=company_id,
            branch_id=branch_id,
            job_id=job_id,
            appointment_id=UUID(int=201),
            visit_sequence=1,
        ),
        SimpleNamespace(
            id=UUID(int=2),
            company_id=company_id,
            branch_id=branch_id,
            job_id=job_id,
            appointment_id=UUID(int=202),
            visit_sequence=2,
        ),
    )
    session = _CorrectionSession(rows)
    corrections = (
        AppointmentCorrection(
            retained(appointment("appt_a", "job_a", 1), 1, 1), 2, "a" * 64
        ),
        AppointmentCorrection(
            retained(appointment("appt_b", "job_a", 2), 2, 2), 1, "b" * 64
        ),
    )
    corrections = tuple(
        AppointmentCorrection(
            RetainedAppointmentProjection(
                link_id=item.retained.link_id,
                job_id=job_id,
                appointment_id=item.retained.appointment_id,
                source_id=item.retained.source_id,
                current_sequence=item.retained.current_sequence,
            ),
            item.corrected_sequence,
            item.digest,
        )
        for item in corrections
    )
    applied = await apply_job_sequence_corrections(
        session,  # type: ignore[arg-type]
        company_id=company_id,
        branch_id=branch_id,
        sequence_plan_id=UUID(int=600),
        failed_child_run_id=UUID(int=601),
        corrections=corrections,
    )
    assert applied == 2
    assert session.flush_states[-1] == (2, 1)
    assert len(session.added) == 2


@pytest.mark.asyncio
async def test_atomic_three_way_reprojection_never_commits_a_collision() -> None:
    company_id, branch_id, job_id = UUID(int=700), UUID(int=701), UUID(int=702)
    rows = tuple(
        SimpleNamespace(
            id=UUID(int=index),
            company_id=company_id,
            branch_id=branch_id,
            job_id=job_id,
            appointment_id=UUID(int=800 + index),
            visit_sequence=index,
        )
        for index in (1, 2, 3)
    )
    session = _CorrectionSession(rows)
    targets = {1: 3, 2: 1, 3: 2}
    corrections = tuple(
        AppointmentCorrection(
            RetainedAppointmentProjection(
                link_id=UUID(int=index),
                job_id=job_id,
                appointment_id=UUID(int=800 + index),
                source_id=f"appt_{index}",
                current_sequence=index,
            ),
            corrected,
            f"{index}" * 64,
        )
        for index, corrected in targets.items()
    )
    await apply_job_sequence_corrections(
        session,  # type: ignore[arg-type]
        company_id=company_id,
        branch_id=branch_id,
        sequence_plan_id=UUID(int=900),
        failed_child_run_id=UUID(int=901),
        corrections=corrections,
    )
    assert session.flush_states[-1] == (3, 1, 2)


@pytest.mark.skipif(
    not (
        Path.home()
        / ".acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z"
    ).exists(),
    reason="protected SOURCE.4 qualification evidence is not installed",
)
def test_sealed_repair_appointment_sequence_population() -> None:
    root = Path.home() / ".acp-enterprise/migration/housecall-pro"
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=root / "hcp-source-4-20260827T223858Z",
        control_csv=root
        / "hcp-source-3-controls/derived/AllCountyPlumbingandLeak_customer_export.csv",
        migration1a_root=root / "hcp-migration-1a-20260828T120000Z",
    )
    original, _ = builder.build(baseline_counts={"business": 0, "masters": 1})
    customers = frozenset(
        item.source_identity for item in original.customers.reviewed.aggregates
    )
    locations = frozenset(
        native
        for item in original.customers.reviewed.aggregates
        for native in item.service_location_source_identities
    )
    repair = builder.build_child_repair_plan(
        original=original,
        persisted_customer_ids=customers,
        persisted_location_ids=locations,
    )
    assert repair.repair_plan_digest == OLD_DIGEST
    sequence = build_appointment_sequence_plan(repair.operational.appointments)
    assert sequence.digest == (
        "9e77ed819ee488ac5114d6fda26d9ae422b081cdfa9785fb56bbf679d6fa7acb"
    )
    assert (
        sequence.job_count,
        sequence.single_visit_job_count,
        sequence.multi_visit_job_count,
        sequence.multi_visit_appointment_count,
        sequence.visits_beyond_first,
        sequence.maximum_visits,
    ) == (992, 911, 81, 338, 257, 36)
