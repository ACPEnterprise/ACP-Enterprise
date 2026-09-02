from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.dispatch.errors import DispatchValidation
from app.dispatch.intelligence import (
    CandidatePlacement,
    EvidenceRef,
    EvidenceState,
    JobDemand,
    TimeWindow,
)
from app.dispatch.intelligence_runtime import (
    AcpDispatchRuntimeAdapter,
    DispatchRecommendationService,
    DurationState,
    MeasuredDuration,
    RuntimeSnapshot,
    aggregate_measured_durations,
    derive_candidate_windows,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
JOB = UUID("30000000-0000-0000-0000-000000000001")
EMPLOYEE = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2027, 3, 1, 12, tzinfo=timezone.utc)
REF = EvidenceRef("synthetic.completed-work", "source-1", "a" * 64)


def _window(start: datetime = NOW, minutes: int = 60) -> TimeWindow:
    return TimeWindow(start, start + timedelta(minutes=minutes))


def _duration(index: int, minutes: int, *, branch_id: UUID = BRANCH) -> MeasuredDuration:
    completed = NOW - timedelta(days=index)
    return MeasuredDuration(
        job_id=UUID(int=index + 10),
        company_id=COMPANY,
        branch_id=branch_id,
        service_category="synthetic_service",
        started_at=completed - timedelta(minutes=minutes),
        completed_at=completed,
        active_minutes=minutes,
        evidence=(EvidenceRef(REF.authority, f"source-{index}", REF.digest),),
    )


def test_duration_history_is_descriptive_deterministic_and_scope_safe() -> None:
    rows = (_duration(1, 30), _duration(2, 60), _duration(3, 90), _duration(4, 999, branch_id=UUID(int=99)))
    kwargs = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "service_category": "synthetic_service",
        "period": _window(NOW - timedelta(days=30), 60 * 24 * 31),
        "measured_at": NOW,
    }
    first = aggregate_measured_durations(rows, **kwargs)
    second = aggregate_measured_durations(tuple(reversed(rows)), **kwargs)
    assert first.state is DurationState.MEASURED_HISTORY_AVAILABLE
    assert (first.sample_count, first.median_minutes, first.minimum_minutes, first.maximum_minutes) == (3, 60, 30, 90)
    assert first.digest == second.digest
    assert all("prediction" in item or "minimum" in item for item in first.limitations)


def test_duration_readiness_fails_closed() -> None:
    kwargs = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "period": _window(NOW - timedelta(days=30), 60 * 24 * 31),
        "measured_at": NOW,
    }
    assert aggregate_measured_durations((), service_category="synthetic", **kwargs).state is DurationState.SOURCE_REQUIRED
    assert aggregate_measured_durations((_duration(1, 30),), service_category="synthetic_service", **kwargs).state is DurationState.INSUFFICIENT_SAMPLE
    assert aggregate_measured_durations((), service_category=None, **kwargs).state is DurationState.CATEGORY_UNCLASSIFIED


def test_candidate_windows_use_only_customer_boundaries_and_scheduled_duration() -> None:
    promised = _window(NOW, 180)
    windows = derive_candidate_windows(promised, 60)
    assert windows == (_window(NOW, 60), _window(NOW + timedelta(hours=2), 60))
    with pytest.raises(DispatchValidation, match="authoritative scheduled duration"):
        derive_candidate_windows(promised, None)


class _Adapter:
    async def snapshot(self, session, *, context, job_id, proposed_windows):
        job = JobDemand(
            company_id=COMPANY,
            branch_id=BRANCH,
            job_id=JOB,
            lifecycle="ready",
            priority="high",
            promised_window=_window(NOW - timedelta(hours=1), 240),
            expected_duration_minutes=60,
            duration_state=EvidenceState.KNOWN,
            required_capabilities=frozenset({"synthetic"}),
            required_certifications=frozenset(),
            evidence=(REF,),
            fleet_required=False,
        )
        candidate = CandidatePlacement(
            company_id=COMPANY,
            branch_id=BRANCH,
            employee_id=EMPLOYEE,
            employee_active=True,
            employee_authorized=True,
            capabilities=frozenset({"synthetic"}),
            certifications=frozenset(),
            availability=(_window(NOW - timedelta(hours=1), 240),),
            availability_state=EvidenceState.KNOWN,
            proposed_window=proposed_windows[0],
            commitments=(),
            downstream_customer_windows=(),
            fleet_state=EvidenceState.UNKNOWN,
            fleet_ready=None,
            travel_state=EvidenceState.EXTERNAL_GATE,
            travel_minutes=None,
            live_field_state="working",
            evidence=(REF,),
        )
        return RuntimeSnapshot(job, (candidate,))


@pytest.mark.asyncio
async def test_runtime_service_is_proposal_only_and_useful_without_routing() -> None:
    result = await DispatchRecommendationService(_Adapter()).recommend(
        object(), context=object(), job_id=JOB, proposed_windows=(_window(),)  # type: ignore[arg-type]
    )
    assert result.mutation_authority == "none"
    assert result.candidates[0].eligible is True
    assert any("Travel" in item for item in result.candidates[0].tradeoffs)
    assert any("external-gated" in item for item in result.limitations)


@pytest.mark.asyncio
async def test_acp_adapter_composes_owning_domain_projections(monkeypatch) -> None:
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(hours=3)
    appointment_id = UUID(int=50)
    detail = SimpleNamespace(
        id=JOB,
        company_id=COMPANY,
        branch_id=BRANCH,
        status=SimpleNamespace(value="ready"),
        priority=SimpleNamespace(value="high"),
        concurrency_version=2,
        updated_at=start,
        appointments=(SimpleNamespace(
            appointment_id=appointment_id,
            arrival_window_start_at=start,
            arrival_window_end_at=end,
            expected_duration_minutes=60,
        ),),
    )
    appointment = SimpleNamespace(
        id=appointment_id, concurrency_version=3, updated_at=start
    )
    employee = SimpleNamespace(
        employee_id=EMPLOYEE,
        branch_id=BRANCH,
        eligible=True,
        capability_codes=("technician",),
        availability_confidence="authoritative",
        decision="eligible",
    )
    async def job_detail(*args, **kwargs):
        return detail
    async def appointment_detail(*args, **kwargs):
        return appointment
    async def board(*args, **kwargs):
        return SimpleNamespace(items=())
    async def eligible(*args, **kwargs):
        return (employee,)
    monkeypatch.setattr("app.dispatch.intelligence_runtime.jobs_query_service.get_job_detail", job_detail)
    monkeypatch.setattr("app.dispatch.intelligence_runtime.scheduling_query_service.get_appointment", appointment_detail)
    monkeypatch.setattr("app.dispatch.intelligence_runtime.dispatch_service.board", board)
    monkeypatch.setattr("app.dispatch.intelligence_runtime.workforce_eligibility_service.eligible_technicians", eligible)
    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY),
        authorized_branch_ids=frozenset({BRANCH}),
        can_access_branch=lambda value: value == BRANCH,
    )
    snapshot = await AcpDispatchRuntimeAdapter().snapshot(
        object(), context=context, job_id=JOB, proposed_windows=()  # type: ignore[arg-type]
    )
    assert len(snapshot.candidates) == 2
    assert all(item.travel_state is EvidenceState.EXTERNAL_GATE for item in snapshot.candidates)
    assert snapshot.job.fleet_required is False
    assert {ref.authority for ref in snapshot.job.evidence} == {"jobs.job-detail", "scheduling.appointment"}
