"""Deterministic Employee/Job labor evidence shared by Payroll and Economics.

The composer joins explicit authority only. Scheduled time never becomes worked
time, assignment never becomes paid time, and unassigned paid time remains an
Employee fact rather than being forced onto a Job.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from typing import Final
from uuid import UUID

CONTRACT_VERSION: Final = "workforce.time-economics-readiness.v1"
MAX_LINKS: Final = 10_000
MAX_INTERVALS: Final = 50_000


class IntervalKind(StrEnum):
    SCHEDULED = "SCHEDULED"
    WORKED = "WORKED"
    JOBSITE = "JOBSITE"
    PAID = "PAID"
    PRODUCTIVE = "PRODUCTIVE"


class Confidence(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    PARTIAL = "PARTIAL"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    authority: str
    record_id: str
    version: str
    digest: str

    def __post_init__(self) -> None:
        if not all((self.authority, self.record_id, self.version, self.digest)):
            raise ValueError("complete provenance is required")


@dataclass(frozen=True, slots=True)
class EmployeeJobLink:
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID | None
    provenance: ProvenanceRef


@dataclass(frozen=True, slots=True)
class LaborInterval:
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    kind: IntervalKind
    start_at: datetime
    end_at: datetime
    provenance: ProvenanceRef
    job_id: UUID | None = None
    appointment_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("labor intervals must be timezone-aware")
        if self.end_at <= self.start_at:
            raise ValueError("labor interval end must follow start")
        if self.kind is IntervalKind.PAID and (
            self.job_id is not None or self.appointment_id is not None
        ):
            raise ValueError("paid time authority does not assign time to a Job")
        if self.kind is not IntervalKind.PAID and self.job_id is None:
            raise ValueError("Job interval requires Job identity")


@dataclass(frozen=True, slots=True)
class JobLaborEvidence:
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID | None
    scheduled_minutes: int | None
    worked_minutes: int | None
    jobsite_minutes: int | None
    paid_overlap_minutes: int | None
    productive_minutes: int | None
    confidence: Confidence
    provenance: tuple[ProvenanceRef, ...]
    missing_inputs: tuple[str, ...]
    conflicts: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class EmployeeLaborEvidence:
    company_id: UUID
    employee_id: UUID
    paid_minutes: int | None
    job_worked_minutes: int | None
    jobsite_minutes: int | None
    productive_minutes: int | None
    unclassified_paid_minutes: int | None
    confidence: Confidence
    job_evidence_digests: tuple[str, ...]
    paid_provenance: tuple[ProvenanceRef, ...]
    missing_inputs: tuple[str, ...]
    conflicts: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class LaborEvidencePacket:
    contract_version: str
    company_id: UUID
    jobs: tuple[JobLaborEvidence, ...]
    employees: tuple[EmployeeLaborEvidence, ...]
    source_readiness: tuple[dict[str, str], ...]
    evidence_digest: str


def compose_labor_evidence(
    *,
    company_id: UUID,
    links: tuple[EmployeeJobLink, ...],
    intervals: tuple[LaborInterval, ...],
) -> LaborEvidencePacket:
    if len(links) > MAX_LINKS or len(intervals) > MAX_INTERVALS:
        raise ValueError("labor evidence input exceeds bounded size")
    if any(link.company_id != company_id for link in links) or any(
        interval.company_id != company_id for interval in intervals
    ):
        raise ValueError("foreign Company labor evidence")
    if len({(x.employee_id, x.job_id, x.appointment_id) for x in links}) != len(links):
        raise ValueError("duplicate Employee/Job/Appointment relationship")
    link_keys = {(x.employee_id, x.job_id, x.appointment_id) for x in links}

    paid_by_employee: dict[UUID, list[LaborInterval]] = defaultdict(list)
    job_intervals: dict[
        tuple[UUID, UUID, UUID | None], list[LaborInterval]
    ] = defaultdict(
        list
    )
    for interval in intervals:
        if interval.kind is IntervalKind.PAID:
            paid_by_employee[interval.employee_id].append(interval)
        else:
            key = (interval.employee_id, interval.job_id, interval.appointment_id)
            if key not in link_keys:
                raise ValueError("Job interval lacks an authoritative assignment link")
            job_intervals[key].append(interval)

    jobs = tuple(
        _job_evidence(
            link,
            job_intervals[(link.employee_id, link.job_id, link.appointment_id)],
            paid_by_employee[link.employee_id],
        )
        for link in sorted(
            links,
            key=lambda x: (
                str(x.employee_id),
                str(x.job_id),
                str(x.appointment_id) if x.appointment_id is not None else "",
            ),
        )
    )
    employees = tuple(
        _employee_evidence(
            company_id,
            employee_id,
            paid_by_employee[employee_id],
            tuple(job for job in jobs if job.employee_id == employee_id),
        )
        for employee_id in sorted(
            {*(x.employee_id for x in links), *paid_by_employee}, key=str
        )
    )
    readiness = source_readiness()
    body = {
        "contract_version": CONTRACT_VERSION,
        "company_id": str(company_id),
        "jobs": [asdict(item) for item in jobs],
        "employees": [asdict(item) for item in employees],
        "source_readiness": readiness,
    }
    return LaborEvidencePacket(
        CONTRACT_VERSION, company_id, jobs, employees, readiness, _digest(body)
    )


def source_readiness() -> tuple[dict[str, str], ...]:
    return (
        {
            "relationship": "employee_job_appointment",
            "authority": "dispatch",
            "state": "AVAILABLE",
            "limitation": "Assignment does not prove work or paid time.",
        },
        {
            "relationship": "scheduled_duration",
            "authority": "scheduling",
            "state": "AVAILABLE",
            "limitation": "Scheduled duration is never substituted for actual work.",
        },
        {
            "relationship": "worked_interval",
            "authority": "jobs_field_service",
            "state": "PARTIAL",
            "limitation": "Requires explicit start/end evidence; missing timestamps remain unknown.",
        },
        {
            "relationship": "jobsite_interval",
            "authority": "dispatch_field_service",
            "state": "PARTIAL",
            "limitation": "Arrival/location evidence must be admitted; no route inference.",
        },
        {
            "relationship": "paid_interval",
            "authority": "timekeeping",
            "state": "AVAILABLE",
            "limitation": "Approved paid time remains Employee-level authority.",
        },
        {
            "relationship": "productive_interval",
            "authority": "operational_measurement",
            "state": "SOURCE_REQUIRED",
            "limitation": "Only explicitly classified evidence qualifies; no Company KPI policy is selected.",
        },
        {
            "relationship": "hcp_operational_evidence",
            "authority": "migration",
            "state": "PARTIAL",
            "limitation": "Only successor-aware, digest-bound admitted evidence may compose.",
        },
        {
            "relationship": "labor_cost_burden",
            "authority": "payroll_policy",
            "state": "POLICY_REQUIRED",
            "limitation": "No rate or burden is inferred.",
        },
    )


def _job_evidence(
    link: EmployeeJobLink, intervals: list[LaborInterval], paid: list[LaborInterval]
) -> JobLaborEvidence:
    conflicts: list[str] = []
    valid: dict[IntervalKind, list[LaborInterval]] = defaultdict(list)
    for interval in intervals:
        if interval.branch_id != link.branch_id:
            conflicts.append(f"foreign_branch:{interval.provenance.record_id}")
            continue
        valid[interval.kind].append(interval)
    for kind, values in valid.items():
        if _has_overlap(values):
            conflicts.append(f"overlapping_{kind.value.lower()}_intervals")
    if _has_overlap(paid):
        conflicts.append("overlapping_paid_intervals")
    scheduled = _minutes(valid[IntervalKind.SCHEDULED])
    worked = _minutes(valid[IntervalKind.WORKED])
    jobsite = _minutes(valid[IntervalKind.JOBSITE])
    productive = _minutes(valid[IntervalKind.PRODUCTIVE])
    if productive is not None and worked is None:
        conflicts.append("productive_without_worked_interval")
    elif productive is not None and worked is not None and productive > worked:
        conflicts.append("productive_time_exceeds_worked_time")
    paid_overlap = (
        _overlap_minutes(valid[IntervalKind.WORKED], paid)
        if worked is not None
        else None
    )
    missing = tuple(
        name
        for name, value in (
            ("worked_interval", worked),
            ("jobsite_interval", jobsite),
            ("paid_interval", paid_overlap),
            ("productive_interval", productive),
        )
        if value is None
    )
    confidence = (
        Confidence.CONFLICTING
        if conflicts
        else (Confidence.AUTHORITATIVE if not missing else Confidence.PARTIAL)
    )
    provenance = tuple(
        sorted(
            {
                link.provenance,
                *(x.provenance for x in intervals),
                *(x.provenance for x in paid),
            },
            key=lambda x: (x.authority, x.record_id, x.digest),
        )
    )
    base = {
        "company_id": str(link.company_id),
        "branch_id": str(link.branch_id),
        "employee_id": str(link.employee_id),
        "job_id": str(link.job_id),
        "appointment_id": str(link.appointment_id),
        "scheduled_minutes": scheduled,
        "worked_minutes": worked,
        "jobsite_minutes": jobsite,
        "paid_overlap_minutes": paid_overlap,
        "productive_minutes": productive,
        "confidence": confidence,
        "provenance": [asdict(x) for x in provenance],
        "missing_inputs": missing,
        "conflicts": tuple(conflicts),
    }
    return JobLaborEvidence(
        link.company_id,
        link.branch_id,
        link.employee_id,
        link.job_id,
        link.appointment_id,
        scheduled,
        worked,
        jobsite,
        paid_overlap,
        productive,
        confidence,
        provenance,
        missing,
        tuple(conflicts),
        (
            "Actual worked duration is distinct from scheduled duration.",
            "Paid overlap is evidence overlap, not payroll allocation or Job labor cost.",
        ),
        _digest(base),
    )


def _employee_evidence(
    company_id: UUID,
    employee_id: UUID,
    paid: list[LaborInterval],
    jobs: tuple[JobLaborEvidence, ...],
) -> EmployeeLaborEvidence:
    conflicts = ["overlapping_paid_intervals"] if _has_overlap(paid) else []
    paid_minutes = _minutes(paid)
    worked = _complete_job_sum(jobs, "worked_minutes")
    jobsite = _complete_job_sum(jobs, "jobsite_minutes")
    productive = _complete_job_sum(jobs, "productive_minutes")
    attributed_overlap = _complete_job_sum(jobs, "paid_overlap_minutes")
    if (
        paid_minutes is not None
        and attributed_overlap is not None
        and attributed_overlap > paid_minutes
    ):
        conflicts.append("job_paid_overlap_exceeds_paid_time")
    unclassified = (
        paid_minutes - attributed_overlap
        if paid_minutes is not None
        and attributed_overlap is not None
        and not conflicts
        else None
    )
    missing = tuple(
        name
        for name, value in (
            ("paid_interval", paid_minutes),
            ("complete_job_worked_intervals", worked),
            ("complete_jobsite_intervals", jobsite),
            ("complete_productive_intervals", productive),
            ("complete_paid_job_overlap", attributed_overlap),
        )
        if value is None
    )
    confidence = (
        Confidence.CONFLICTING
        if conflicts
        else (
            Confidence.AUTHORITATIVE
            if paid_minutes is not None
            and all(x.confidence is Confidence.AUTHORITATIVE for x in jobs)
            else Confidence.PARTIAL
        )
    )
    job_digests = tuple(x.evidence_digest for x in jobs)
    provenance = tuple(
        sorted(
            {x.provenance for x in paid},
            key=lambda x: (x.authority, x.record_id, x.digest),
        )
    )
    base = {
        "company_id": str(company_id),
        "employee_id": str(employee_id),
        "paid_minutes": paid_minutes,
        "job_worked_minutes": worked,
        "jobsite_minutes": jobsite,
        "productive_minutes": productive,
        "unclassified_paid_minutes": unclassified,
        "confidence": confidence,
        "jobs": job_digests,
        "paid_provenance": [asdict(x) for x in provenance],
        "missing_inputs": missing,
        "conflicts": tuple(conflicts),
    }
    return EmployeeLaborEvidence(
        company_id,
        employee_id,
        paid_minutes,
        worked,
        jobsite,
        productive,
        unclassified,
        confidence,
        job_digests,
        provenance,
        missing,
        tuple(conflicts),
        (
            "Unclassified paid time is not presumed nonproductive.",
            "No compensation, labor burden, ranking, or employment conclusion is produced.",
        ),
        _digest(base),
    )


def _minutes(intervals: list[LaborInterval]) -> int | None:
    return (
        sum(int((x.end_at - x.start_at).total_seconds() // 60) for x in intervals)
        if intervals
        else None
    )


def _complete_job_sum(
    jobs: tuple[JobLaborEvidence, ...], attribute: str
) -> int | None:
    """Return a total only when every attributed Job supplies the measurement."""
    if not jobs:
        return None
    values = tuple(getattr(item, attribute) for item in jobs)
    return sum(values) if all(value is not None for value in values) else None


def _overlap_minutes(
    left: list[LaborInterval], right: list[LaborInterval]
) -> int | None:
    if not right:
        return None
    return sum(
        max(
            int(
                (min(a.end_at, b.end_at) - max(a.start_at, b.start_at)).total_seconds()
                // 60
            ),
            0,
        )
        for a in left
        for b in right
    )


def _has_overlap(intervals: list[LaborInterval]) -> bool:
    ordered = sorted(intervals, key=lambda x: (x.start_at, x.end_at))
    return any(current.start_at < prior.end_at for prior, current in pairwise(ordered))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
