"""Deterministic Job Participation evidence reconciled to approved paid time.

Workday Time remains the authority for paid minutes.  Participation assertions only
attribute portions of an approved time-entry revision to a Job or an explicit non-Job
activity; they cannot create paid time, compensation, withholding, or Payroll results.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from uuid import UUID

CONTRACT_VERSION = "timekeeping.job-participation-reconciliation.v1"


class JobParticipationError(ValueError):
    pass


class ParticipationKind(StrEnum):
    JOB = "job"
    TRAVEL = "travel"
    NONPRODUCTIVE = "nonproductive"


@dataclass(frozen=True, slots=True)
class ApprovedPaidTimeEvidence:
    revision_id: UUID
    evidence_digest: str
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    start_at: datetime
    end_at: datetime
    approved: bool


@dataclass(frozen=True, slots=True)
class ParticipationAssertion:
    assertion_id: UUID
    evidence_digest: str
    paid_time_revision_id: UUID
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    kind: ParticipationKind
    start_at: datetime
    end_at: datetime
    job_id: UUID | None
    approved: bool


@dataclass(frozen=True, slots=True)
class ParticipationCorrection:
    predecessor_assertion_id: UUID
    successor: ParticipationAssertion
    correction_kind: str
    reason: str
    reviewed_by_user_id: UUID
    evidence_digest: str


def correct_participation(
    *,
    predecessor: ParticipationAssertion,
    successor_id: UUID,
    replacement_job_id: UUID,
    reason: str,
    reviewed_by_user_id: UUID,
) -> ParticipationCorrection:
    """Create immutable successor evidence for an incorrect Job attribution."""

    _validate_assertion_shape(predecessor)
    if predecessor.kind is not ParticipationKind.JOB:
        raise JobParticipationError("only Job participation has Job attribution")
    if not reason.strip():
        raise JobParticipationError("correction reason is required")
    if replacement_job_id == predecessor.job_id:
        raise JobParticipationError("replacement Job must differ from predecessor")
    canonical = {
        "contract": CONTRACT_VERSION,
        "predecessor_assertion_id": str(predecessor.assertion_id),
        "predecessor_digest": predecessor.evidence_digest,
        "successor_id": str(successor_id),
        "replacement_job_id": str(replacement_job_id),
        "reason": reason.strip(),
        "reviewed_by_user_id": str(reviewed_by_user_id),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    successor = ParticipationAssertion(
        assertion_id=successor_id,
        evidence_digest=digest,
        paid_time_revision_id=predecessor.paid_time_revision_id,
        company_id=predecessor.company_id,
        branch_id=predecessor.branch_id,
        employee_id=predecessor.employee_id,
        kind=ParticipationKind.JOB,
        start_at=predecessor.start_at,
        end_at=predecessor.end_at,
        job_id=replacement_job_id,
        approved=True,
    )
    return ParticipationCorrection(
        predecessor.assertion_id,
        successor,
        "incorrect_job",
        reason.strip(),
        reviewed_by_user_id,
        digest,
    )


@dataclass(frozen=True, slots=True)
class JobMinutes:
    job_id: UUID
    minutes: int


@dataclass(frozen=True, slots=True)
class JobParticipationReconciliation:
    contract: str
    company_id: UUID
    employee_id: UUID
    paid_minutes: int
    attributed_minutes: int
    job_minutes: tuple[JobMinutes, ...]
    travel_minutes: int
    nonproductive_minutes: int
    unclassified_minutes: int
    accepted_assertion_ids: tuple[UUID, ...]
    blockers: tuple[str, ...]
    evidence_digest: str

    @property
    def payroll_ready(self) -> bool:
        """Attribution completeness only; never authorizes Payroll execution."""

        return not self.blockers and self.unclassified_minutes == 0


def reconcile_job_participation(
    paid_time: ApprovedPaidTimeEvidence,
    assertions: tuple[ParticipationAssertion, ...],
) -> JobParticipationReconciliation:
    """Reconcile explicit participation to one approved paid-time revision.

    Gaps remain unclassified rather than being inferred from Appointments or elapsed
    wall time. Unapproved assertions are visible blockers and contribute no minutes.
    """

    _validate_paid_time(paid_time)
    blockers: list[str] = []
    accepted: list[ParticipationAssertion] = []
    assertion_ids: set[UUID] = set()
    for value in assertions:
        _validate_assertion_shape(value)
        if value.assertion_id in assertion_ids:
            raise JobParticipationError("duplicate participation assertion identity")
        assertion_ids.add(value.assertion_id)
        if (
            value.company_id != paid_time.company_id
            or value.branch_id != paid_time.branch_id
            or value.employee_id != paid_time.employee_id
            or value.paid_time_revision_id != paid_time.revision_id
        ):
            raise JobParticipationError("participation assertion scope mismatch")
        if value.start_at < paid_time.start_at or value.end_at > paid_time.end_at:
            raise JobParticipationError("participation exceeds approved paid time")
        if not value.approved:
            blockers.append("UNAPPROVED_PARTICIPATION")
            continue
        accepted.append(value)

    accepted.sort(key=lambda item: (item.start_at, item.end_at, str(item.assertion_id)))
    for previous, current in pairwise(accepted):
        if current.start_at < previous.end_at:
            raise JobParticipationError("participation assertions overlap")

    job_totals: dict[UUID, int] = defaultdict(int)
    travel = 0
    nonproductive = 0
    for value in accepted:
        minutes = _minutes(value.start_at, value.end_at)
        if value.kind is ParticipationKind.JOB:
            assert value.job_id is not None
            job_totals[value.job_id] += minutes
        elif value.kind is ParticipationKind.TRAVEL:
            travel += minutes
        else:
            nonproductive += minutes
    paid_minutes = _minutes(paid_time.start_at, paid_time.end_at)
    attributed = sum(job_totals.values()) + travel + nonproductive
    unclassified = paid_minutes - attributed
    if unclassified:
        blockers.append("UNCLASSIFIED_PAID_TIME")
    if not paid_time.approved:
        blockers.append("PAID_TIME_NOT_APPROVED")

    job_minutes = tuple(
        JobMinutes(job_id, minutes)
        for job_id, minutes in sorted(job_totals.items(), key=lambda item: str(item[0]))
    )
    accepted_ids = tuple(item.assertion_id for item in accepted)
    canonical = {
        "contract": CONTRACT_VERSION,
        "paid_time": {
            "revision_id": str(paid_time.revision_id),
            "evidence_digest": paid_time.evidence_digest,
        },
        "assertions": [
            {
                "assertion_id": str(item.assertion_id),
                "evidence_digest": item.evidence_digest,
            }
            for item in accepted
        ],
        "job_minutes": [
            {"job_id": str(item.job_id), "minutes": item.minutes}
            for item in job_minutes
        ],
        "travel_minutes": travel,
        "nonproductive_minutes": nonproductive,
        "unclassified_minutes": unclassified,
        "blockers": sorted(set(blockers)),
    }
    return JobParticipationReconciliation(
        contract=CONTRACT_VERSION,
        company_id=paid_time.company_id,
        employee_id=paid_time.employee_id,
        paid_minutes=paid_minutes,
        attributed_minutes=attributed,
        job_minutes=job_minutes,
        travel_minutes=travel,
        nonproductive_minutes=nonproductive,
        unclassified_minutes=unclassified,
        accepted_assertion_ids=accepted_ids,
        blockers=tuple(sorted(set(blockers))),
        evidence_digest=hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def _validate_paid_time(value: ApprovedPaidTimeEvidence) -> None:
    if value.start_at.tzinfo is None or value.end_at.tzinfo is None:
        raise JobParticipationError("paid time must be timezone-aware")
    if value.end_at <= value.start_at or not _digest_valid(value.evidence_digest):
        raise JobParticipationError("paid-time evidence is invalid")


def _validate_assertion_shape(value: ParticipationAssertion) -> None:
    if value.start_at.tzinfo is None or value.end_at.tzinfo is None:
        raise JobParticipationError("participation time must be timezone-aware")
    if value.end_at <= value.start_at or not _digest_valid(value.evidence_digest):
        raise JobParticipationError("participation evidence is invalid")
    if (value.kind is ParticipationKind.JOB) != (value.job_id is not None):
        raise JobParticipationError(
            "Job identity is required only for Job participation"
        )


def _minutes(start: datetime, end: datetime) -> int:
    seconds = int((end - start).total_seconds())
    if seconds % 60:
        raise JobParticipationError(
            "participation evidence must resolve to whole minutes"
        )
    return seconds // 60


def _digest_valid(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
