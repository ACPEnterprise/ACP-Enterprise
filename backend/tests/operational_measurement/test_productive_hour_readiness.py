from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.operational_measurement.labor_evidence import (
    EmployeeJobLink,
    IntervalKind,
    LaborInterval,
    ProvenanceRef,
    compose_labor_evidence,
)
from app.operational_measurement.productive_hour_readiness import (
    ProductiveHourMeasure,
    ReadinessState,
    SupplementalTimeFact,
    build_productive_hour_readiness,
)

START = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)


def ref(authority: str, identity: str) -> ProvenanceRef:
    return ProvenanceRef(authority, identity, "v1", f"digest-{identity}")


def labor_packet(*, include_worked: bool = True):
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    link = EmployeeJobLink(
        company, branch, employee, job, appointment, ref("dispatch", "assignment")
    )
    intervals = [
        LaborInterval(
            company,
            None,
            employee,
            IntervalKind.PAID,
            START,
            START + timedelta(hours=8),
            ref("timekeeping", "paid"),
        ),
        LaborInterval(
            company,
            branch,
            employee,
            IntervalKind.SCHEDULED,
            START,
            START + timedelta(hours=6),
            ref("scheduling", "scheduled"),
            job,
            appointment,
        ),
    ]
    if include_worked:
        intervals.extend(
            (
                LaborInterval(
                    company,
                    branch,
                    employee,
                    IntervalKind.WORKED,
                    START + timedelta(hours=1),
                    START + timedelta(hours=6),
                    ref("jobs", "worked"),
                    job,
                    appointment,
                ),
                LaborInterval(
                    company,
                    branch,
                    employee,
                    IntervalKind.JOBSITE,
                    START + timedelta(minutes=45),
                    START + timedelta(hours=6, minutes=15),
                    ref("dispatch", "jobsite"),
                    job,
                    appointment,
                ),
                LaborInterval(
                    company,
                    branch,
                    employee,
                    IntervalKind.PRODUCTIVE,
                    START + timedelta(hours=1, minutes=30),
                    START + timedelta(hours=5, minutes=30),
                    ref("operations", "productive"),
                    job,
                    appointment,
                ),
            )
        )
    return compose_labor_evidence(
        company_id=company, links=(link,), intervals=tuple(intervals)
    ), (company, branch, employee, job, appointment)


def measures(scope):
    return {item.measure: item for item in scope.measures}


def test_complete_evidence_is_distinct_at_all_measurement_scopes():
    labor, ids = labor_packet()
    company, branch, employee, job, appointment = ids
    supplemental = (
        SupplementalTimeFact(
            company,
            branch,
            employee,
            ProductiveHourMeasure.TRAVEL_MINUTES,
            ReadinessState.AVAILABLE,
            45,
            (ref("dispatch", "travel"),),
            job,
            appointment,
        ),
        SupplementalTimeFact(
            company,
            branch,
            employee,
            ProductiveHourMeasure.NONPRODUCTIVE_OPERATIONAL_MINUTES,
            ReadinessState.AVAILABLE,
            30,
            (ref("operations", "nonproductive"),),
            job,
            appointment,
        ),
    )
    packet = build_productive_hour_readiness(labor, supplemental=supplemental)
    job_values = measures(packet.jobs[0])
    assert job_values[ProductiveHourMeasure.SCHEDULED_MINUTES].minutes == 360
    assert job_values[ProductiveHourMeasure.ACTUAL_WORKED_MINUTES].minutes == 300
    assert job_values[ProductiveHourMeasure.JOBSITE_MINUTES].minutes == 330
    assert job_values[ProductiveHourMeasure.PRODUCTIVE_JOB_MINUTES].minutes == 240
    assert job_values[ProductiveHourMeasure.PAID_MINUTES].minutes == 300
    assert job_values[ProductiveHourMeasure.TRAVEL_MINUTES].minutes == 45
    assert len(packet.branches) == 1
    assert packet.company.company_id == company
    assert packet.employees[0].employee_id == employee


def test_missing_actual_time_is_absent_and_schedule_never_substitutes():
    labor, _ = labor_packet(include_worked=False)
    packet = build_productive_hour_readiness(labor)
    values = measures(packet.jobs[0])
    assert (
        values[ProductiveHourMeasure.SCHEDULED_MINUTES].state
        is ReadinessState.AVAILABLE
    )
    assert values[ProductiveHourMeasure.SCHEDULED_MINUTES].minutes == 360
    assert (
        values[ProductiveHourMeasure.ACTUAL_WORKED_MINUTES].state
        is ReadinessState.ABSENT
    )
    assert values[ProductiveHourMeasure.ACTUAL_WORKED_MINUTES].minutes is None
    assert values[ProductiveHourMeasure.TRAVEL_MINUTES].state is ReadinessState.ABSENT


def test_partial_and_conflicting_operational_evidence_never_emit_partial_total():
    labor, ids = labor_packet()
    company, branch, employee, job, appointment = ids
    partial = SupplementalTimeFact(
        company,
        branch,
        employee,
        ProductiveHourMeasure.TRAVEL_MINUTES,
        ReadinessState.PARTIAL,
        None,
        (),
        job,
        appointment,
        ("route_provider",),
    )
    conflicting = SupplementalTimeFact(
        company,
        branch,
        employee,
        ProductiveHourMeasure.NONPRODUCTIVE_OPERATIONAL_MINUTES,
        ReadinessState.CONFLICTING,
        None,
        (),
        job,
        appointment,
        (),
        ("overlapping_classification",),
    )
    values = measures(
        build_productive_hour_readiness(
            labor, supplemental=(partial, conflicting)
        ).jobs[0]
    )
    assert values[ProductiveHourMeasure.TRAVEL_MINUTES].state is ReadinessState.PARTIAL
    assert values[ProductiveHourMeasure.TRAVEL_MINUTES].minutes is None
    assert (
        values[ProductiveHourMeasure.NONPRODUCTIVE_OPERATIONAL_MINUTES].state
        is ReadinessState.CONFLICTING
    )


def test_paid_time_stays_employee_specific_and_multi_technician_job_is_not_collapsed():
    _, ids = labor_packet()
    company, branch, _, job, appointment = ids
    second_employee = uuid4()
    second_link = EmployeeJobLink(
        company,
        branch,
        second_employee,
        job,
        appointment,
        ref("dispatch", "assignment-2"),
    )
    second_intervals = (
        LaborInterval(
            company,
            None,
            second_employee,
            IntervalKind.PAID,
            START,
            START + timedelta(hours=4),
            ref("timekeeping", "paid-2"),
        ),
        LaborInterval(
            company,
            branch,
            second_employee,
            IntervalKind.WORKED,
            START,
            START + timedelta(hours=2),
            ref("jobs", "worked-2"),
            job,
            appointment,
        ),
    )
    combined = compose_labor_evidence(
        company_id=company,
        links=(
            EmployeeJobLink(
                company, branch, ids[2], job, appointment, ref("dispatch", "assignment")
            ),
            second_link,
        ),
        intervals=tuple(
            LaborInterval(
                x.company_id,
                x.branch_id,
                x.employee_id,
                x.kind,
                x.start_at,
                x.end_at,
                x.provenance,
                x.job_id,
                x.appointment_id,
            )
            for x in (
                LaborInterval(
                    company,
                    None,
                    ids[2],
                    IntervalKind.PAID,
                    START,
                    START + timedelta(hours=8),
                    ref("timekeeping", "paid"),
                ),
                LaborInterval(
                    company,
                    branch,
                    ids[2],
                    IntervalKind.WORKED,
                    START,
                    START + timedelta(hours=5),
                    ref("jobs", "worked"),
                    job,
                    appointment,
                ),
                *second_intervals,
            )
        ),
    )
    packet = build_productive_hour_readiness(combined)
    assert len(packet.jobs) == 2
    assert {
        scope.employee_id: measures(scope)[
            ProductiveHourMeasure.ACTUAL_WORKED_MINUTES
        ].minutes
        for scope in packet.jobs
    } == {ids[2]: 300, second_employee: 120}


def test_supplemental_evidence_requires_authoritative_relationship_and_company():
    labor, ids = labor_packet()
    company, branch, employee, _, _ = ids
    orphan = SupplementalTimeFact(
        company,
        branch,
        employee,
        ProductiveHourMeasure.TRAVEL_MINUTES,
        ReadinessState.AVAILABLE,
        10,
        (ref("dispatch", "orphan"),),
        uuid4(),
        uuid4(),
    )
    with pytest.raises(ValueError, match="lacks labor relationship"):
        build_productive_hour_readiness(labor, supplemental=(orphan,))
    foreign = SupplementalTimeFact(
        uuid4(),
        branch,
        employee,
        ProductiveHourMeasure.TRAVEL_MINUTES,
        ReadinessState.AVAILABLE,
        10,
        (ref("dispatch", "foreign"),),
    )
    with pytest.raises(ValueError, match="foreign Company"):
        build_productive_hour_readiness(labor, supplemental=(foreign,))


def test_downstream_contract_has_policy_gates_and_no_actions():
    labor, _ = labor_packet()
    downstream = build_productive_hour_readiness(labor).downstream_contract
    assert "break_even_method" in downstream["policy_required"]
    assert "labor_burden_method" in downstream["policy_required"]
    assert downstream["employment_action"] is None
    assert downstream["pricing_action"] is None
