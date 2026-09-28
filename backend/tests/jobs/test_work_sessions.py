from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.jobs.work_sessions import (
    ActivityAction,
    ContinuationReason,
    JobActivity,
    JobActivityEvent,
    JobContinuation,
    JobPlan,
    JobWorkSessionError,
    WorkPattern,
    derive_activity_intervals,
)


def event(*, action: ActivityAction, activity: JobActivity | None, minute: int, scope: tuple, key: str) -> JobActivityEvent:
    company, branch, employee, job, appointment = scope
    return JobActivityEvent(uuid4(), company, branch, employee, job, appointment, action, activity, datetime(2026, 9, 28, 13, minute, tzinfo=timezone.utc), 3, 2, key, key * 8)


def test_parts_run_preserves_one_job_and_exact_activity_durations() -> None:
    scope = tuple(uuid4() for _ in range(5))
    intervals = derive_activity_intervals((
        event(action=ActivityAction.START, activity=JobActivity.WORKING, minute=0, scope=scope, key="start-work"),
        event(action=ActivityAction.CHANGE, activity=JobActivity.PARTS_RUN, minute=10, scope=scope, key="parts-run"),
        event(action=ActivityAction.CHANGE, activity=JobActivity.WORKING, minute=25, scope=scope, key="resume-work"),
        event(action=ActivityAction.FINISH_VISIT, activity=None, minute=55, scope=scope, key="finish-day"),
    ))
    assert [value.activity for value in intervals] == [JobActivity.WORKING, JobActivity.PARTS_RUN, JobActivity.WORKING]
    assert [value.duration_seconds for value in intervals] == [600, 900, 1800]
    assert {value.job_id for value in intervals} == {scope[3]}


def test_activity_fails_closed_on_cross_visit_transition() -> None:
    scope = tuple(uuid4() for _ in range(5))
    other = (*scope[:4], uuid4())
    with pytest.raises(JobWorkSessionError, match="scope differs"):
        derive_activity_intervals((
            event(action=ActivityAction.START, activity=JobActivity.WORKING, minute=0, scope=scope, key="start-work"),
            event(action=ActivityAction.FINISH_VISIT, activity=None, minute=10, scope=other, key="finish-day"),
        ))


def test_unknown_plan_remains_unknown_and_continuation_does_not_clone_job() -> None:
    assert JobPlan() == JobPlan(pattern=None)
    scope = tuple(uuid4() for _ in range(5))
    continuation = JobContinuation(*scope, ContinuationReason.MULTI_DAY_PLANNED, date(2026, 9, 29), False)
    assert continuation.job_id == scope[3]
    assert continuation.appointment_id == scope[4]
    assert JobPlan(pattern=WorkPattern.MULTI_DAY, estimated_visits=3).estimated_visits == 3


def test_invalid_planning_and_other_reason_fail_closed() -> None:
    with pytest.raises(JobWorkSessionError):
        JobPlan(estimated_visits=0)
    with pytest.raises(JobWorkSessionError):
        JobContinuation(*(uuid4() for _ in range(5)), ContinuationReason.OTHER, None, True)
