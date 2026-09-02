"""Deterministic, proposal-only dispatch recommendation foundation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Final, cast
from uuid import UUID, uuid5

CONTRACT_VERSION: Final = "dispatch.recommendation.v1"
ENGINE_VERSION: Final = "dispatch-deterministic-1"
MAX_CANDIDATES: Final = 50
MAX_SLOTS_PER_CANDIDATE: Final = 24
MAX_HORIZON_DAYS: Final = 14
_NAMESPACE = UUID("59ea9134-8f87-4da8-b886-6587528429cc")


class EvidenceState(StrEnum):
    KNOWN = "KNOWN"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    POLICY_REQUIRED = "POLICY_REQUIRED"
    EXTERNAL_GATE = "EXTERNAL_GATE"


class ConstraintResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class PlacementClass(StrEnum):
    BEST_OVERALL_FIT = "BEST_OVERALL_FIT"
    EARLIER_BUT_DISRUPTIVE = "EARLIER_BUT_DISRUPTIVE"
    LATER_LOWER_TRAVEL = "LATER_LOWER_TRAVEL"
    CAPABILITY_LIMITED = "CAPABILITY_LIMITED"
    CONFLICTED = "CONFLICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    authority: str
    identity: str
    digest: str


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        if self.end_at <= self.start_at:
            raise ValueError("time window must have positive duration")
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("time window must be timezone-aware")

    def overlaps(self, other: TimeWindow) -> bool:
        return self.start_at < other.end_at and self.end_at > other.start_at


@dataclass(frozen=True, slots=True)
class JobDemand:
    company_id: UUID
    branch_id: UUID
    job_id: UUID
    lifecycle: str
    priority: str
    promised_window: TimeWindow
    expected_duration_minutes: int | None
    duration_state: EvidenceState
    required_capabilities: frozenset[str]
    required_certifications: frozenset[str]
    evidence: tuple[EvidenceRef, ...]
    fleet_required: bool = True


@dataclass(frozen=True, slots=True)
class CandidatePlacement:
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    employee_active: bool
    employee_authorized: bool
    capabilities: frozenset[str]
    certifications: frozenset[str]
    availability: tuple[TimeWindow, ...]
    availability_state: EvidenceState
    proposed_window: TimeWindow
    commitments: tuple[TimeWindow, ...]
    downstream_customer_windows: tuple[TimeWindow, ...]
    fleet_state: EvidenceState
    fleet_ready: bool | None
    travel_state: EvidenceState
    travel_minutes: int | None
    live_field_state: str | None
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ConstraintEvidence:
    constraint: str
    result: ConstraintResult
    explanation: str


@dataclass(frozen=True, slots=True)
class PlacementRecommendation:
    employee_id: UUID
    proposed_window: TimeWindow
    placement_class: PlacementClass
    eligible: bool
    rank: int | None
    constraints: tuple[ConstraintEvidence, ...]
    tradeoffs: tuple[str, ...]
    limitations: tuple[str, ...]
    confidence: EvidenceState


@dataclass(frozen=True, slots=True)
class DispatchRecommendation:
    recommendation_id: UUID
    contract_version: str
    engine_version: str
    job_id: UUID
    company_id: UUID
    branch_id: UUID
    candidates: tuple[PlacementRecommendation, ...]
    risk_conditions: tuple[dict[str, str], ...]
    recovery_options: tuple[dict[str, str], ...]
    evidence: tuple[EvidenceRef, ...]
    limitations: tuple[str, ...]
    recommendation_digest: str
    mutation_authority: str = "none"


def recommend_dispatch(
    job: JobDemand, candidates: tuple[CandidatePlacement, ...]
) -> DispatchRecommendation:
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError("candidate population exceeds deterministic bound")
    if job.lifecycle not in {"draft", "ready", "in_progress", "paused"}:
        raise ValueError("Job lifecycle does not admit a placement recommendation")
    if job.expected_duration_minutes is not None and job.expected_duration_minutes <= 0:
        raise ValueError("expected duration must be positive")

    evaluated = [_evaluate(job, candidate) for candidate in candidates]
    eligible = [item for item in evaluated if item[1]]
    eligible.sort(key=lambda item: item[0])
    rank_by_key = {
        (item[2].employee_id, item[2].proposed_window.start_at): index + 1
        for index, item in enumerate(eligible)
    }
    recommendations = []
    for _, is_eligible, recommendation in sorted(
        evaluated,
        key=lambda item: (
            not item[1],
            item[0],
            str(item[2].employee_id),
            item[2].proposed_window.start_at,
        ),
    ):
        rank = rank_by_key.get(
            (recommendation.employee_id, recommendation.proposed_window.start_at)
        )
        placement_class = recommendation.placement_class
        if rank == 1:
            placement_class = PlacementClass.BEST_OVERALL_FIT
        recommendations.append(
            replace(
                recommendation,
                placement_class=placement_class,
                rank=rank,
            )
        )

    risk_conditions = _risks(job, tuple(recommendations))
    recovery_options = _recovery_options(tuple(recommendations), risk_conditions)
    evidence = tuple(
        sorted(
            {
                item
                for item in (
                    *job.evidence,
                    *(ref for candidate in candidates for ref in candidate.evidence),
                )
            },
            key=lambda item: (item.authority, item.identity, item.digest),
        )
    )
    limitations = _global_limitations(job, candidates)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "job_id": str(job.job_id),
        "company_id": str(job.company_id),
        "branch_id": str(job.branch_id),
        "candidates": [_normalize(item) for item in recommendations],
        "risk_conditions": risk_conditions,
        "recovery_options": recovery_options,
        "evidence": [_normalize(item) for item in evidence],
        "limitations": limitations,
        "mutation_authority": "none",
    }
    digest = _digest(payload)
    return DispatchRecommendation(
        recommendation_id=uuid5(_NAMESPACE, digest),
        contract_version=CONTRACT_VERSION,
        engine_version=ENGINE_VERSION,
        job_id=job.job_id,
        company_id=job.company_id,
        branch_id=job.branch_id,
        candidates=tuple(recommendations),
        risk_conditions=tuple(risk_conditions),
        recovery_options=tuple(recovery_options),
        evidence=evidence,
        limitations=tuple(limitations),
        recommendation_digest=digest,
    )


def _evaluate(
    job: JobDemand, candidate: CandidatePlacement
) -> tuple[tuple[object, ...], bool, PlacementRecommendation]:
    constraints = (
        _boolean(
            "company_scope",
            candidate.company_id == job.company_id,
            "Candidate must belong to the Job Company.",
        ),
        _boolean(
            "branch_scope",
            candidate.branch_id == job.branch_id,
            "Candidate must belong to the Job Branch.",
        ),
        _boolean(
            "active_employee", candidate.employee_active, "Employee must be active."
        ),
        _boolean(
            "employee_authority",
            candidate.employee_authorized,
            "Current assignment authority is required.",
        ),
        _set_constraint(
            "capability", job.required_capabilities, candidate.capabilities
        ),
        _set_constraint(
            "certification", job.required_certifications, candidate.certifications
        ),
        _availability_constraint(candidate),
        _boolean(
            "appointment_conflict",
            not any(
                candidate.proposed_window.overlaps(item)
                for item in candidate.commitments
            ),
            "Proposed placement cannot overlap an existing commitment.",
        ),
        _boolean(
            "customer_window",
            _contained(candidate.proposed_window, job.promised_window),
            "Placement must preserve the promised Customer window.",
        ),
        _fleet_constraint(job, candidate),
        _duration_constraint(job),
    )
    failed = [item for item in constraints if item.result is ConstraintResult.FAIL]
    unknown = [item for item in constraints if item.result is ConstraintResult.UNKNOWN]
    eligible = not failed and not unknown
    downstream_risk = sum(
        candidate.proposed_window.overlaps(item)
        or candidate.proposed_window.end_at > item.start_at
        for item in candidate.downstream_customer_windows
    )
    disruption = sum(
        candidate.proposed_window.overlaps(item) for item in candidate.commitments
    )
    tradeoffs = []
    if downstream_risk:
        tradeoffs.append(
            f"Placement creates {downstream_risk} downstream Customer-window risk(s)."
        )
    if (
        candidate.travel_state is EvidenceState.KNOWN
        and candidate.travel_minutes is not None
    ):
        tradeoffs.append(
            f"Authoritative travel evidence reports {candidate.travel_minutes} minutes."
        )
    elif candidate.travel_state is not EvidenceState.KNOWN:
        tradeoffs.append("Travel duration is unavailable and is not estimated.")
    if candidate.live_field_state in {"en_route", "arrived", "working", "paused"}:
        tradeoffs.append(
            f"Current field state is {candidate.live_field_state}; schedule impact requires inspection."
        )
    limitations = [item.explanation for item in unknown]
    if failed:
        placement_class = (
            PlacementClass.CAPABILITY_LIMITED
            if any(
                item.constraint in {"capability", "certification"} for item in failed
            )
            else PlacementClass.CONFLICTED
        )
    elif unknown:
        placement_class = PlacementClass.INSUFFICIENT_EVIDENCE
    elif disruption or downstream_risk:
        placement_class = PlacementClass.EARLIER_BUT_DISRUPTIVE
    elif candidate.travel_state is EvidenceState.KNOWN:
        placement_class = PlacementClass.LATER_LOWER_TRAVEL
    else:
        placement_class = PlacementClass.INSUFFICIENT_EVIDENCE
    confidence = (
        EvidenceState.KNOWN
        if eligible and candidate.travel_state is EvidenceState.KNOWN
        else EvidenceState.UNKNOWN
    )
    score = (
        len(failed),
        len(unknown),
        downstream_risk,
        disruption,
        candidate.travel_minutes
        if candidate.travel_state is EvidenceState.KNOWN
        and candidate.travel_minutes is not None
        else 10**9,
        candidate.proposed_window.start_at,
        str(candidate.employee_id),
    )
    return (
        score,
        eligible,
        PlacementRecommendation(
            employee_id=candidate.employee_id,
            proposed_window=candidate.proposed_window,
            placement_class=placement_class,
            eligible=eligible,
            rank=None,
            constraints=constraints,
            tradeoffs=tuple(tradeoffs),
            limitations=tuple(limitations),
            confidence=confidence,
        ),
    )


def _boolean(name: str, passed: bool, explanation: str) -> ConstraintEvidence:
    return ConstraintEvidence(
        name, ConstraintResult.PASS if passed else ConstraintResult.FAIL, explanation
    )


def _set_constraint(
    name: str, required: frozenset[str], actual: frozenset[str]
) -> ConstraintEvidence:
    missing = sorted(required - actual)
    return ConstraintEvidence(
        name,
        ConstraintResult.FAIL if missing else ConstraintResult.PASS,
        f"Missing required {name}: {', '.join(missing)}"
        if missing
        else f"Required {name} evidence is present.",
    )


def _availability_constraint(candidate: CandidatePlacement) -> ConstraintEvidence:
    if candidate.availability_state is not EvidenceState.KNOWN:
        return ConstraintEvidence(
            "availability",
            ConstraintResult.UNKNOWN,
            f"Employee availability is {candidate.availability_state.value.lower()}.",
        )
    return _boolean(
        "availability",
        any(
            _contained(candidate.proposed_window, item)
            for item in candidate.availability
        ),
        "Proposed placement must be contained in authoritative availability.",
    )


def _fleet_constraint(
    job: JobDemand, candidate: CandidatePlacement
) -> ConstraintEvidence:
    if not job.fleet_required:
        return ConstraintEvidence(
            "fleet_readiness",
            ConstraintResult.PASS,
            "No authoritative Fleet requirement applies to this Job.",
        )
    if (
        candidate.fleet_state is not EvidenceState.KNOWN
        or candidate.fleet_ready is None
    ):
        return ConstraintEvidence(
            "fleet_readiness",
            ConstraintResult.UNKNOWN,
            "Fleet readiness is not authoritative for this placement.",
        )
    return _boolean(
        "fleet_readiness",
        candidate.fleet_ready,
        "Required Fleet evidence must report ready.",
    )


def _duration_constraint(job: JobDemand) -> ConstraintEvidence:
    if (
        job.duration_state is not EvidenceState.KNOWN
        or job.expected_duration_minutes is None
    ):
        return ConstraintEvidence(
            "job_duration",
            ConstraintResult.UNKNOWN,
            "Job duration is unknown; no prediction is invented.",
        )
    return ConstraintEvidence(
        "job_duration",
        ConstraintResult.PASS,
        "Scheduled duration evidence is present; it is not a predicted duration.",
    )


def _contained(inner: TimeWindow, outer: TimeWindow) -> bool:
    return inner.start_at >= outer.start_at and inner.end_at <= outer.end_at


def _risks(
    job: JobDemand, recommendations: tuple[PlacementRecommendation, ...]
) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    if not any(item.eligible for item in recommendations):
        risks.append(
            {
                "condition": "UNASSIGNED_HIGH_PRIORITY_JOB"
                if job.priority in {"high", "urgent", "emergency"}
                else "CAPABILITY_EVIDENCE_MISSING",
                "state": "OPEN",
                "beacon_authority": "evaluation_only",
            }
        )
    for item in recommendations:
        failed = {
            constraint.constraint
            for constraint in item.constraints
            if constraint.result is ConstraintResult.FAIL
        }
        if "appointment_conflict" in failed:
            risks.append(
                {
                    "condition": "ASSIGNMENT_CONFLICT",
                    "state": "OPEN",
                    "beacon_authority": "evaluation_only",
                }
            )
        if "fleet_readiness" in failed:
            risks.append(
                {
                    "condition": "FLEET_READINESS_CONFLICT",
                    "state": "OPEN",
                    "beacon_authority": "evaluation_only",
                }
            )
        if any(
            "downstream Customer-window risk" in tradeoff for tradeoff in item.tradeoffs
        ):
            risks.append(
                {
                    "condition": "DOWNSTREAM_WINDOW_AT_RISK",
                    "state": "OPEN",
                    "beacon_authority": "evaluation_only",
                }
            )
    if any(item.eligible for item in recommendations) and risks:
        risks.append(
            {
                "condition": "RECOVERY_OPTION_AVAILABLE",
                "state": "OBSERVED",
                "beacon_authority": "evaluation_only",
            }
        )
    unique = sorted({tuple(sorted(item.items())) for item in risks})
    return [dict(item) for item in unique]


def _recovery_options(
    recommendations: tuple[PlacementRecommendation, ...], risks: list[dict[str, str]]
) -> list[dict[str, str]]:
    options = [
        {
            "action": "LEAVE_UNCHANGED",
            "authority": "dispatcher_required",
            "effect": "Preserves the current schedule while the dispatcher inspects risk.",
        }
    ]
    if any(item.eligible for item in recommendations):
        options.append(
            {
                "action": "ACCEPT_CANDIDATE_PLACEMENT",
                "authority": "dispatcher_required",
                "effect": "Uses existing Scheduling/Dispatch mutation contracts after explicit approval.",
            }
        )
    if risks:
        options.extend(
            (
                {
                    "action": "MOVE_JOB_LATER",
                    "authority": "dispatcher_required",
                    "effect": "Candidate only; Customer commitment must be revalidated.",
                },
                {
                    "action": "REQUEST_CUSTOMER_CONFIRMATION",
                    "authority": "dispatcher_required",
                    "effect": "Does not send communication automatically.",
                },
            )
        )
    return options


def _global_limitations(
    job: JobDemand, candidates: tuple[CandidatePlacement, ...]
) -> list[str]:
    values = [
        "Recommendation is a proposal and has no assignment or scheduling authority.",
        "No Employee performance score or autonomous mutation is produced.",
    ]
    if any(item.travel_state is not EvidenceState.KNOWN for item in candidates):
        values.append(
            "Travel remains external-gated where authoritative routing evidence is absent."
        )
    if job.duration_state is not EvidenceState.KNOWN:
        values.append(
            "Duration prediction remains source-gated; unknown duration fails closed."
        )
    values.append(
        "Ranking uses deterministic constraint ordering; owner weighting policy is not invented."
    )
    return values


def reevaluation_triggers() -> tuple[str, ...]:
    return (
        "new_job",
        "appointment_created",
        "appointment_rescheduled",
        "technician_en_route",
        "technician_arrived",
        "job_started",
        "job_paused",
        "job_completed",
        "job_completed_early",
        "job_running_late",
        "employee_availability_changed",
        "fleet_unavailable",
        "customer_window_changed",
        "appointment_cancelled",
    )


def _normalize(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, frozenset | tuple | list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(cast(Any, value)))
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
