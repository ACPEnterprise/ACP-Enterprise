from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.main import app
from app.payroll.contracts import PayrollConflictError
from app.payroll.finalization import PayrollGrossResultService
from app.payroll.operations import PayrollOperationsService
from app.timekeeping.job_participation import (
    CorrectionState,
    IntervalConfidence,
    IntervalValidity,
    WorkedIntervalSource,
)
from app.timekeeping.query_service import WorkdayTimeQueryService
from app.timekeeping.schemas import JobWorkedIntervalView, PayPeriodView


def revision(
    *,
    start_hour: int,
    duration_hours: int,
    state: str = "approved",
    revision_number: int = 1,
    corrected: bool = False,
):
    started = datetime(2026, 9, 7, start_hour, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        entry_id=uuid4(),
        revision_number=revision_number,
        work_date=date(2026, 9, 7),
        start_at=started,
        end_at=started + timedelta(hours=duration_hours),
        approved_duration_minutes=None,
        created_at=started,
        provenance="employee_punch",
        state=state,
        approved_at=started if state == "approved" else None,
        correction_reason="Manager correction" if corrected else None,
        evidence_digest="a" * 64,
    )


def test_timecard_days_preserve_overlap_correction_and_unclassified_time() -> None:
    first = revision(start_hour=8, duration_hours=4)
    second = revision(
        start_hour=11,
        duration_hours=3,
        state="corrected",
        revision_number=2,
        corrected=True,
    )
    days = WorkdayTimeQueryService._operation_days([first, second])  # type: ignore[list-item]
    assert len(days) == 1
    day = days[0]
    assert day.total_supported_minutes == 420
    assert day.job_minutes is None
    assert day.non_job_supported_minutes is None
    assert day.unclassified_minutes == 420
    assert day.has_overlap is True
    assert day.has_correction is True
    assert day.review_state == "NEEDS_REVIEW"
    assert all(item.overlap for item in day.intervals)
    assert {item.attribution_state for item in day.intervals} == {"UNCLASSIFIED"}


def test_payroll_candidates_only_project_persisted_calculation_components() -> None:
    service = PayrollOperationsService()
    assert service._earning_minutes(None) == (None, None)


def test_payroll_readiness_uses_successor_authority_without_false_conflict() -> None:
    service = PayrollOperationsService()
    ancestor_id = uuid4()
    successor_id = uuid4()
    values = (
        SimpleNamespace(id=ancestor_id, supersedes_policy_id=None),
        SimpleNamespace(id=successor_id, supersedes_policy_id=ancestor_id),
    )
    assert service._remove_superseded(values, "supersedes_policy_id") == (values[1],)
    persisted = SimpleNamespace(
        earning_components=[
            {"component_type": "regular", "payable_minutes": 2400},
            {"component_type": "overtime_premium", "payable_minutes": 300},
            {"component_type": "additional", "payable_minutes": 60},
        ]
    )
    assert service._earning_minutes(persisted) == (2400, 300)


def test_period_operations_are_bounded_read_only_routes() -> None:
    paths = app.openapi()["paths"]
    timecard = paths["/api/v1/timekeeping/admin/pay-periods/{pay_period_id}/timecards"]
    payroll = paths["/api/v1/payroll/operations/pay-periods/{pay_period_id}"]
    labor = paths[
        "/api/v1/timekeeping/admin/pay-periods/{pay_period_id}/job-labor-actuals"
    ]
    assert set(timecard) == {"get"}
    assert set(payroll) == {"get"}
    assert set(labor) == {"get"}


class _ScalarRows:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def all(self) -> tuple[object, ...]:
        return self._values


class _SnapshotSession:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    async def scalars(self, statement: object) -> _ScalarRows:
        return _ScalarRows(self._values)


@pytest.mark.asyncio
async def test_payroll_snapshot_fails_closed_when_current_time_evidence_changes() -> None:
    original_id, corrected_id = uuid4(), uuid4()
    snapshot = SimpleNamespace(approved_revision_ids=[str(original_id)])
    with pytest.raises(PayrollConflictError, match="stale"):
        await PayrollGrossResultService._require_current_time_snapshot(
            _SnapshotSession((corrected_id,)),  # type: ignore[arg-type]
            company_id=uuid4(),
            employee_id=uuid4(),
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 7),
            snapshot=snapshot,  # type: ignore[arg-type]
        )

    await PayrollGrossResultService._require_current_time_snapshot(
        _SnapshotSession((original_id,)),  # type: ignore[arg-type]
        company_id=uuid4(),
        employee_id=uuid4(),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 7),
        snapshot=snapshot,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_job_labor_queue_preserves_actual_and_paid_time_distinction() -> None:
    employee_id, job_id, interval_id, revision_id = uuid4(), uuid4(), uuid4(), uuid4()
    start = datetime(2026, 9, 7, 8, tzinfo=timezone.utc)
    actual = JobWorkedIntervalView(
        interval_id=interval_id,
        revision_id=revision_id,
        revision_number=1,
        employee_id=employee_id,
        job_id=job_id,
        appointment_id=None,
        start_at=start,
        stop_at=start + timedelta(hours=2),
        duration_seconds=7200,
        source=WorkedIntervalSource.EMPLOYEE_CLOCK,
        correction_state=CorrectionState.ORIGINAL,
        supersedes_revision_id=None,
        audit_lineage=(revision_id,),
        source_event_ids=(uuid4(), uuid4()),
        validity=IntervalValidity.VALID,
        confidence=IntervalConfidence.AUTHORITATIVE,
        evidence_digest="a" * 64,
        correction_reason=None,
        corrected_by_user_id=None,
    )
    operations = SimpleNamespace(
        pay_period=PayPeriodView(
            id=uuid4(),
            period_start=date(2026, 9, 7),
            period_end=date(2026, 9, 13),
            processing_date=date(2026, 9, 14),
            payday=date(2026, 9, 18),
            timezone="America/New_York",
            schedule_definition_id="synthetic-weekly",
            schedule_version=1,
        ),
        employees=(
            SimpleNamespace(
                employee_id=employee_id,
                employee_number="SYN-1",
                display_name="Synthetic Employee",
                job_intervals=(actual,),
                days=(),
            ),
        ),
    )

    class Queries(WorkdayTimeQueryService):
        async def admin_operations(self, *args: object, **kwargs: object) -> object:
            return operations

    queue = await Queries(None).job_labor_actuals(  # type: ignore[arg-type]
        None, context=SimpleNamespace(), pay_period_id=operations.pay_period.id  # type: ignore[arg-type]
    )
    assert queue.accepted_interval_count == 1
    assert queue.total_accepted_seconds == 7200
    assert queue.items[0].paid_time_reconciliation == "PAID_TIME_UNAVAILABLE"
    assert "PAID_TIME_UNAVAILABLE" in queue.items[0].exception_codes
