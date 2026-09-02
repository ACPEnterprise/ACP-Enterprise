"""Runtime composition for proposal-only Dispatch Intelligence.

The adapter boundary deliberately consumes owning-domain projections.  The pure
recommendation engine never queries persistence and this service never mutates
Scheduling or Dispatch authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from statistics import median
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.errors import DispatchNotFound, DispatchValidation
from app.dispatch.intelligence import (
    MAX_CANDIDATES,
    MAX_HORIZON_DAYS,
    MAX_SLOTS_PER_CANDIDATE,
    CandidatePlacement,
    DispatchRecommendation,
    EvidenceRef,
    EvidenceState,
    JobDemand,
    TimeWindow,
    recommend_dispatch,
)
from app.dispatch.service import dispatch_service
from app.jobs.errors import JobNotFoundError
from app.jobs.query import JobDetailQuery
from app.jobs.query_service import jobs_query_service
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.query import AppointmentQuery
from app.scheduling.query_service import scheduling_query_service
from app.workforce.query import WorkforceEligibilityQuery
from app.workforce.query_service import workforce_eligibility_service

RUNTIME_CONTRACT_VERSION = "dispatch.runtime-snapshot.v1"
DURATION_CONTRACT_VERSION = "dispatch.measured-duration.v1"
ROUTING_CONTRACT_VERSION = "dispatch.travel-evidence.v1"


class DurationState(StrEnum):
    MEASURED_HISTORY_AVAILABLE = "MEASURED_HISTORY_AVAILABLE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    STALE_HISTORY = "STALE_HISTORY"
    CATEGORY_UNCLASSIFIED = "CATEGORY_UNCLASSIFIED"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"


@dataclass(frozen=True, slots=True)
class MeasuredDuration:
    job_id: UUID
    company_id: UUID
    branch_id: UUID
    service_category: str | None
    started_at: datetime
    completed_at: datetime
    active_minutes: int
    evidence: tuple[EvidenceRef, ...]
    corrected: bool = False

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("duration timestamps must be timezone-aware")
        if self.completed_at <= self.started_at or self.active_minutes <= 0:
            raise ValueError("measured duration must be positive")


@dataclass(frozen=True, slots=True)
class DurationAggregate:
    contract_version: str
    company_id: UUID
    branch_id: UUID
    service_category: str | None
    period: TimeWindow
    state: DurationState
    sample_count: int
    median_minutes: int | None
    minimum_minutes: int | None
    maximum_minutes: int | None
    measured_through: datetime | None
    evidence: tuple[EvidenceRef, ...]
    limitations: tuple[str, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class TravelEvidenceRequest:
    company_id: UUID
    branch_id: UUID
    origin_location_ref: str
    destination_location_ref: str
    departure_at: datetime
    source_digest: str


@dataclass(frozen=True, slots=True)
class TravelEvidence:
    contract_version: str
    request_digest: str
    duration_minutes: int
    distance_meters: int | None
    provider: str
    provider_version: str
    calculated_at: datetime
    state: EvidenceState
    limitations: tuple[str, ...]
    evidence_digest: str


class RoutingEvidenceProvider(Protocol):
    async def evaluate(self, request: TravelEvidenceRequest) -> TravelEvidence: ...


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    job: JobDemand
    candidates: tuple[CandidatePlacement, ...]
    contract_version: str = RUNTIME_CONTRACT_VERSION


class DispatchRuntimeAdapter(Protocol):
    async def snapshot(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        proposed_windows: tuple[TimeWindow, ...],
    ) -> RuntimeSnapshot: ...


def aggregate_measured_durations(
    rows: tuple[MeasuredDuration, ...],
    *,
    company_id: UUID,
    branch_id: UUID,
    service_category: str | None,
    period: TimeWindow,
    measured_at: datetime,
    minimum_samples: int = 3,
    stale_after: timedelta = timedelta(days=180),
) -> DurationAggregate:
    """Build descriptive history; the result is never a duration prediction."""
    if measured_at.tzinfo is None or minimum_samples < 1:
        raise ValueError("duration aggregation controls are invalid")
    accepted = tuple(
        row
        for row in rows
        if row.company_id == company_id
        and row.branch_id == branch_id
        and row.service_category == service_category
        and period.start_at <= row.completed_at < period.end_at
    )
    if service_category is None:
        state = DurationState.CATEGORY_UNCLASSIFIED
    elif not accepted:
        state = DurationState.SOURCE_REQUIRED
    elif len(accepted) < minimum_samples:
        state = DurationState.INSUFFICIENT_SAMPLE
    elif max(row.completed_at for row in accepted) < measured_at - stale_after:
        state = DurationState.STALE_HISTORY
    else:
        state = DurationState.MEASURED_HISTORY_AVAILABLE
    values = sorted(row.active_minutes for row in accepted)
    refs = tuple(sorted({ref for row in accepted for ref in row.evidence}, key=lambda r: (r.authority, r.identity, r.digest)))
    limitations = (
        "Historical measured duration is descriptive evidence, not a prediction.",
        f"Engineering safety minimum is {minimum_samples} accepted samples; owner scheduling policy is not implied.",
    )
    payload = {
        "contract": DURATION_CONTRACT_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id),
        "category": service_category,
        "period": [period.start_at.isoformat(), period.end_at.isoformat()],
        "state": state.value,
        "values": values,
        "evidence": [(r.authority, r.identity, r.digest) for r in refs],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return DurationAggregate(
        DURATION_CONTRACT_VERSION,
        company_id,
        branch_id,
        service_category,
        period,
        state,
        len(values),
        int(median(values)) if values else None,
        values[0] if values else None,
        values[-1] if values else None,
        max((row.completed_at for row in accepted), default=None),
        refs,
        limitations,
        digest,
    )


def derive_candidate_windows(
    promised_window: TimeWindow, scheduled_duration_minutes: int | None
) -> tuple[TimeWindow, ...]:
    """Derive boundary-aligned slots without inventing working hours or cadence."""
    if scheduled_duration_minutes is None:
        raise DispatchValidation(
            "Candidate generation requires authoritative scheduled duration."
        )
    duration = timedelta(minutes=scheduled_duration_minutes)
    if (
        duration <= timedelta(0)
        or duration > promised_window.end_at - promised_window.start_at
    ):
        raise DispatchValidation("Scheduled duration does not fit the Customer window.")
    starts = (promised_window.start_at, promised_window.end_at - duration)
    return tuple(
        TimeWindow(start, start + duration) for start in dict.fromkeys(starts)
    )


class AcpDispatchRuntimeAdapter:
    """Compose scoped Job, Scheduling, Dispatch, and Workforce projections."""

    async def snapshot(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        proposed_windows: tuple[TimeWindow, ...],
    ) -> RuntimeSnapshot:
        if len(proposed_windows) > MAX_SLOTS_PER_CANDIDATE:
            raise DispatchValidation("Candidate window population exceeds its bound.")
        try:
            detail = await jobs_query_service.get_job_detail(
                session, context=context, query=JobDetailQuery(job_id=job_id)
            )
        except JobNotFoundError as error:
            raise DispatchNotFound("Job was not found.") from error
        if not context.can_access_branch(detail.branch_id):
            raise DispatchNotFound("Job was not found.")
        appointment = next((item for item in detail.appointments if item.arrival_window_start_at and item.arrival_window_end_at), None)
        if appointment is None:
            raise DispatchValidation("Job has no authoritative Customer window.")
        promised_start = appointment.arrival_window_start_at
        promised_end = appointment.arrival_window_end_at
        if promised_start is None or promised_end is None:
            raise DispatchValidation("Job has no authoritative Customer window.")
        promised = TimeWindow(promised_start, promised_end)
        if not proposed_windows:
            proposed_windows = derive_candidate_windows(
                promised, appointment.expected_duration_minutes
            )
        now = datetime.now(timezone.utc)
        if any(
            window.start_at < now - timedelta(days=1)
            or window.end_at > now + timedelta(days=MAX_HORIZON_DAYS)
            for window in proposed_windows
        ):
            raise DispatchValidation("Candidate window is outside the bounded horizon.")
        if any(window.start_at < promised.start_at or window.end_at > promised.end_at for window in proposed_windows):
            raise DispatchValidation("Candidate window violates the authoritative Customer window.")
        appointment_record = await scheduling_query_service.get_appointment(
            session,
            context=context,
            query=AppointmentQuery(
                company_id=context.company.id,
                authorized_branch_ids=context.authorized_branch_ids,
                appointment_id=appointment.appointment_id,
            ),
        )
        evidence = (
            _ref("jobs.job-detail", detail.id, detail.concurrency_version, detail.updated_at),
            _ref("scheduling.appointment", appointment_record.id, appointment_record.concurrency_version, appointment_record.updated_at),
        )
        job = JobDemand(
            company_id=detail.company_id,
            branch_id=detail.branch_id,
            job_id=detail.id,
            lifecycle=detail.status.value,
            priority=detail.priority.value,
            promised_window=promised,
            expected_duration_minutes=appointment.expected_duration_minutes,
            duration_state=EvidenceState.KNOWN if appointment.expected_duration_minutes else EvidenceState.UNKNOWN,
            required_capabilities=frozenset(),
            required_certifications=frozenset(),
            evidence=evidence,
            fleet_required=False,
        )
        board = await dispatch_service.board(
            session,
            context=context,
            start_at=min(window.start_at for window in proposed_windows),
            end_at=max(window.end_at for window in proposed_windows) + timedelta(days=1),
            branch_id=detail.branch_id,
        )
        candidates: list[CandidatePlacement] = []
        for window in proposed_windows:
            eligible = await workforce_eligibility_service.eligible_technicians(
                session,
                context=context,
                query=WorkforceEligibilityQuery(
                    company_id=context.company.id,
                    authorized_branch_ids=context.authorized_branch_ids,
                    branch_id=detail.branch_id,
                    window_start_at=window.start_at,
                    window_end_at=window.end_at,
                    exclude_appointment_id=appointment.appointment_id,
                ),
            )
            for employee in eligible:
                commitments = tuple(
                    TimeWindow(item.window_start_at, item.window_end_at)
                    for item in board.items
                    if item.assignment is not None
                    and item.assignment.primary_employee_id == employee.employee_id
                    and item.appointment_id != appointment.appointment_id
                )
                candidates.append(
                    CandidatePlacement(
                        company_id=context.company.id,
                        branch_id=employee.branch_id,
                        employee_id=employee.employee_id,
                        employee_active=True,
                        employee_authorized=employee.eligible,
                        capabilities=frozenset(employee.capability_codes),
                        certifications=frozenset(),
                        availability=(window,) if employee.eligible else (),
                        availability_state=_availability_state(employee.availability_confidence),
                        proposed_window=window,
                        commitments=commitments,
                        downstream_customer_windows=tuple(item for item in commitments if item.start_at >= window.end_at),
                        fleet_state=EvidenceState.UNKNOWN,
                        fleet_ready=None,
                        travel_state=EvidenceState.EXTERNAL_GATE,
                        travel_minutes=None,
                        live_field_state=_live_state(board.items, employee.employee_id),
                        evidence=(_ref("workforce.eligibility", employee.employee_id, employee.decision, employee.availability_confidence),),
                    )
                )
        if len(candidates) > MAX_CANDIDATES:
            raise DispatchValidation("Runtime candidate population exceeds its bound.")
        return RuntimeSnapshot(job=job, candidates=tuple(candidates))


class DispatchRecommendationService:
    def __init__(self, adapter: DispatchRuntimeAdapter | None = None) -> None:
        self._adapter = adapter or AcpDispatchRuntimeAdapter()

    async def recommend(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        proposed_windows: tuple[TimeWindow, ...],
    ) -> DispatchRecommendation:
        snapshot = await self._adapter.snapshot(
            session, context=context, job_id=job_id, proposed_windows=proposed_windows
        )
        return recommend_dispatch(snapshot.job, snapshot.candidates)


def _ref(authority: str, identity: object, *version: object) -> EvidenceRef:
    digest = hashlib.sha256("|".join(str(item) for item in (authority, identity, *version)).encode()).hexdigest()
    return EvidenceRef(authority, str(identity), digest)


def _availability_state(value: str) -> EvidenceState:
    return EvidenceState.KNOWN if value.lower() in {"known", "authoritative", "high"} else EvidenceState.UNKNOWN


def _live_state(items: tuple[object, ...], employee_id: UUID) -> str | None:
    for item in items:
        assignment = getattr(item, "assignment", None)
        if assignment is not None and assignment.primary_employee_id == employee_id:
            return assignment.arrival_state
    return None


dispatch_recommendation_service = DispatchRecommendationService()
