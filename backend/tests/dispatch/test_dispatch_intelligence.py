from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.dispatch.intelligence import (
    CandidatePlacement,
    EvidenceRef,
    EvidenceState,
    JobDemand,
    PlacementClass,
    TimeWindow,
    recommend_dispatch,
    reevaluation_triggers,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
JOB = UUID("30000000-0000-0000-0000-000000000001")
MELVIN = UUID("40000000-0000-0000-0000-000000000001")
ALEX = UUID("40000000-0000-0000-0000-000000000002")
START = datetime(2027, 2, 1, 14, tzinfo=timezone.utc)
REF = EvidenceRef("synthetic.authority", "synthetic-1", "a" * 64)


def window(start: datetime = START, minutes: int = 60) -> TimeWindow:
    return TimeWindow(start, start + timedelta(minutes=minutes))


def job(**changes: object) -> JobDemand:
    values = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "job_id": JOB,
        "lifecycle": "ready",
        "priority": "urgent",
        "promised_window": window(START - timedelta(hours=1), 240),
        "expected_duration_minutes": 60,
        "duration_state": EvidenceState.KNOWN,
        "required_capabilities": frozenset({"technician", "synthetic_service"}),
        "required_certifications": frozenset({"synthetic_cert"}),
        "evidence": (REF,),
    }
    values.update(changes)
    return JobDemand(**values)  # type: ignore[arg-type]


def candidate(employee_id: UUID = MELVIN, **changes: object) -> CandidatePlacement:
    values = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "employee_id": employee_id,
        "employee_active": True,
        "employee_authorized": True,
        "capabilities": frozenset({"technician", "synthetic_service"}),
        "certifications": frozenset({"synthetic_cert"}),
        "availability": (window(START - timedelta(hours=2), 480),),
        "availability_state": EvidenceState.KNOWN,
        "proposed_window": window(),
        "commitments": (),
        "downstream_customer_windows": (),
        "fleet_state": EvidenceState.KNOWN,
        "fleet_ready": True,
        "travel_state": EvidenceState.KNOWN,
        "travel_minutes": 20,
        "live_field_state": None,
        "evidence": (REF,),
    }
    values.update(changes)
    return CandidatePlacement(**values)  # type: ignore[arg-type]


def test_ranking_is_deterministic_explainable_and_proposal_only() -> None:
    later = candidate(
        ALEX, proposed_window=window(START + timedelta(hours=1)), travel_minutes=10
    )
    first = recommend_dispatch(job(), (later, candidate()))
    second = recommend_dispatch(job(), (candidate(), later))
    assert first.recommendation_digest == second.recommendation_digest
    assert first.recommendation_id == second.recommendation_id
    assert first.candidates[0].placement_class is PlacementClass.BEST_OVERALL_FIT
    assert first.candidates[0].rank == 1
    assert first.mutation_authority == "none"
    assert all(
        item["authority"] == "dispatcher_required" for item in first.recovery_options
    )


@pytest.mark.parametrize(
    ("change", "constraint"),
    [
        ({"company_id": UUID(int=99)}, "company_scope"),
        ({"branch_id": UUID(int=98)}, "branch_scope"),
        ({"employee_active": False}, "active_employee"),
        ({"employee_authorized": False}, "employee_authority"),
        ({"capabilities": frozenset({"technician"})}, "capability"),
        ({"certifications": frozenset()}, "certification"),
        ({"fleet_ready": False}, "fleet_readiness"),
        ({"commitments": (window(),)}, "appointment_conflict"),
    ],
)
def test_hard_constraints_fail_closed(
    change: dict[str, object], constraint: str
) -> None:
    result = recommend_dispatch(job(), (candidate(**change),))
    assert result.candidates[0].eligible is False
    assert any(
        item.constraint == constraint and item.result == "FAIL"
        for item in result.candidates[0].constraints
    )


def test_unknown_is_not_pass_and_does_not_invent_travel_or_duration() -> None:
    result = recommend_dispatch(
        job(expected_duration_minutes=None, duration_state=EvidenceState.UNKNOWN),
        (candidate(travel_state=EvidenceState.EXTERNAL_GATE, travel_minutes=None),),
    )
    placement = result.candidates[0]
    assert placement.eligible is False
    assert placement.placement_class is PlacementClass.INSUFFICIENT_EVIDENCE
    assert any(
        item.constraint == "job_duration" and item.result == "UNKNOWN"
        for item in placement.constraints
    )
    assert any("Travel remains external-gated" in item for item in result.limitations)


def test_customer_commitment_outranks_earlier_placement() -> None:
    outside = candidate(proposed_window=window(START - timedelta(hours=2)))
    result = recommend_dispatch(job(), (outside, candidate(ALEX)))
    assert result.candidates[0].employee_id == ALEX
    rejected = next(item for item in result.candidates if item.employee_id == MELVIN)
    assert rejected.eligible is False
    assert any(
        item.constraint == "customer_window" and item.result == "FAIL"
        for item in rejected.constraints
    )


def test_downstream_risk_and_conflict_produce_beacon_evidence_not_signal_authority() -> (
    None
):
    risky = candidate(
        downstream_customer_windows=(window(START + timedelta(minutes=30)),)
    )
    result = recommend_dispatch(job(), (risky,))
    assert any(
        item["condition"] == "DOWNSTREAM_WINDOW_AT_RISK"
        for item in result.risk_conditions
    )
    assert all(
        item["beacon_authority"] == "evaluation_only" for item in result.risk_conditions
    )


def test_empty_or_bounded_population_and_triggers() -> None:
    result = recommend_dispatch(job(), ())
    assert any(
        item["condition"] == "UNASSIGNED_HIGH_PRIORITY_JOB"
        for item in result.risk_conditions
    )
    with pytest.raises(ValueError, match="population exceeds"):
        recommend_dispatch(
            job(), tuple(candidate(UUID(int=index + 1)) for index in range(51))
        )
    assert "fleet_unavailable" in reevaluation_triggers()
    assert "technician_en_route" in reevaluation_triggers()
