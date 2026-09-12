from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.operational_measurement.labor_evidence import (
    Confidence,
    EmployeeJobLink,
    IntervalKind,
    LaborInterval,
    ProvenanceRef,
    compose_labor_evidence,
    source_readiness,
)

START = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)


def provenance(authority: str, record_id: str) -> ProvenanceRef:
    return ProvenanceRef(authority, record_id, "v1", f"digest-{record_id}")


def interval(
    company, branch, employee, kind, start, end, *, job=None, appointment=None
):
    return LaborInterval(
        company,
        branch,
        employee,
        kind,
        start,
        end,
        provenance(kind.value.lower(), str(uuid4())),
        job,
        appointment,
    )


def test_deterministic_employee_job_appointment_labor_relationship():
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    link = EmployeeJobLink(
        company,
        branch,
        employee,
        job,
        appointment,
        provenance("dispatch", "assignment-1"),
    )
    intervals = (
        interval(
            company,
            branch,
            employee,
            IntervalKind.PAID,
            START,
            START + timedelta(hours=9),
        ),
        interval(
            company,
            branch,
            employee,
            IntervalKind.SCHEDULED,
            START + timedelta(hours=1),
            START + timedelta(hours=6),
            job=job,
            appointment=appointment,
        ),
        interval(
            company,
            branch,
            employee,
            IntervalKind.WORKED,
            START + timedelta(hours=2),
            START + timedelta(hours=6, minutes=30),
            job=job,
            appointment=appointment,
        ),
        interval(
            company,
            branch,
            employee,
            IntervalKind.JOBSITE,
            START + timedelta(hours=1, minutes=45),
            START + timedelta(hours=6, minutes=45),
            job=job,
            appointment=appointment,
        ),
        interval(
            company,
            branch,
            employee,
            IntervalKind.PRODUCTIVE,
            START + timedelta(hours=2, minutes=15),
            START + timedelta(hours=6),
            job=job,
            appointment=appointment,
        ),
    )
    packet = compose_labor_evidence(
        company_id=company, links=(link,), intervals=intervals
    )
    replay = compose_labor_evidence(
        company_id=company, links=(link,), intervals=tuple(reversed(intervals))
    )
    evidence = packet.jobs[0]
    assert evidence.scheduled_minutes == 300
    assert evidence.worked_minutes == 270
    assert evidence.jobsite_minutes == 300
    assert evidence.paid_overlap_minutes == 270
    assert evidence.productive_minutes == 225
    assert evidence.confidence is Confidence.AUTHORITATIVE
    assert packet.employees[0].paid_minutes == 540
    assert packet.employees[0].unclassified_paid_minutes == 270
    assert packet.evidence_digest == replay.evidence_digest


def test_authoritative_job_only_clock_interval_composes_without_appointment():
    company, branch, employee, job = (uuid4() for _ in range(4))
    link = EmployeeJobLink(
        company,
        branch,
        employee,
        job,
        None,
        provenance("jobs_field_service", "job-assignment"),
    )
    worked = interval(
        company,
        branch,
        employee,
        IntervalKind.WORKED,
        START,
        START + timedelta(minutes=91),
        job=job,
        appointment=None,
    )

    packet = compose_labor_evidence(
        company_id=company, links=(link,), intervals=(worked,)
    )

    assert packet.jobs[0].appointment_id is None
    assert packet.jobs[0].worked_minutes == 91
    assert packet.jobs[0].scheduled_minutes is None
    assert "paid_interval" in packet.jobs[0].missing_inputs


def test_missing_actual_work_never_falls_back_to_schedule():
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    link = EmployeeJobLink(
        company,
        branch,
        employee,
        job,
        appointment,
        provenance("dispatch", "assignment"),
    )
    scheduled = interval(
        company,
        branch,
        employee,
        IntervalKind.SCHEDULED,
        START,
        START + timedelta(hours=4),
        job=job,
        appointment=appointment,
    )
    evidence = compose_labor_evidence(
        company_id=company, links=(link,), intervals=(scheduled,)
    ).jobs[0]
    assert evidence.scheduled_minutes == 240
    assert evidence.worked_minutes is None
    assert evidence.paid_overlap_minutes is None
    assert evidence.confidence is Confidence.PARTIAL
    assert "worked_interval" in evidence.missing_inputs


def test_multi_technician_job_preserves_separate_employee_evidence():
    company, branch, job, appointment = (uuid4() for _ in range(4))
    employees = (uuid4(), uuid4())
    links = tuple(
        EmployeeJobLink(
            company,
            branch,
            employee,
            job,
            appointment,
            provenance("dispatch", f"assignment-{index}"),
        )
        for index, employee in enumerate(employees)
    )
    intervals = tuple(
        interval(
            company,
            branch,
            employee,
            IntervalKind.WORKED,
            START,
            START + timedelta(hours=index + 1),
            job=job,
            appointment=appointment,
        )
        for index, employee in enumerate(employees)
    )
    packet = compose_labor_evidence(
        company_id=company, links=links, intervals=intervals
    )
    assert {item.employee_id: item.worked_minutes for item in packet.jobs} == {
        employees[0]: 60,
        employees[1]: 120,
    }
    assert len(packet.employees) == 2


def test_paid_time_is_employee_level_and_cannot_claim_job_identity():
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    with pytest.raises(ValueError, match="does not assign"):
        interval(
            company,
            branch,
            employee,
            IntervalKind.PAID,
            START,
            START + timedelta(hours=1),
            job=job,
            appointment=appointment,
        )


def test_foreign_company_branch_and_overlaps_fail_closed():
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    link = EmployeeJobLink(
        company,
        branch,
        employee,
        job,
        appointment,
        provenance("dispatch", "assignment"),
    )
    foreign = interval(
        uuid4(),
        branch,
        employee,
        IntervalKind.WORKED,
        START,
        START + timedelta(hours=1),
        job=job,
        appointment=appointment,
    )
    with pytest.raises(ValueError, match="foreign Company"):
        compose_labor_evidence(company_id=company, links=(link,), intervals=(foreign,))
    worked = (
        interval(
            company,
            branch,
            employee,
            IntervalKind.WORKED,
            START,
            START + timedelta(hours=2),
            job=job,
            appointment=appointment,
        ),
        interval(
            company,
            branch,
            employee,
            IntervalKind.WORKED,
            START + timedelta(hours=1),
            START + timedelta(hours=3),
            job=job,
            appointment=appointment,
        ),
    )
    evidence = compose_labor_evidence(
        company_id=company, links=(link,), intervals=worked
    ).jobs[0]
    assert evidence.confidence is Confidence.CONFLICTING
    assert "overlapping_worked_intervals" in evidence.conflicts


def test_orphan_job_interval_and_unsupported_productive_precision_fail_closed():
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    orphan = interval(
        company,
        branch,
        employee,
        IntervalKind.WORKED,
        START,
        START + timedelta(hours=1),
        job=job,
        appointment=appointment,
    )
    with pytest.raises(ValueError, match="authoritative assignment"):
        compose_labor_evidence(company_id=company, links=(), intervals=(orphan,))
    link = EmployeeJobLink(
        company,
        branch,
        employee,
        job,
        appointment,
        provenance("dispatch", "assignment"),
    )
    productive = interval(
        company,
        branch,
        employee,
        IntervalKind.PRODUCTIVE,
        START,
        START + timedelta(hours=1),
        job=job,
        appointment=appointment,
    )
    evidence = compose_labor_evidence(
        company_id=company, links=(link,), intervals=(productive,)
    ).jobs[0]
    assert evidence.confidence is Confidence.CONFLICTING
    assert "productive_without_worked_interval" in evidence.conflicts


def test_hcp_and_policy_gates_remain_explicit():
    readiness = {row["relationship"]: row["state"] for row in source_readiness()}
    assert readiness["hcp_operational_evidence"] == "PARTIAL"
    assert readiness["productive_interval"] == "SOURCE_REQUIRED"
    assert readiness["labor_cost_burden"] == "POLICY_REQUIRED"
