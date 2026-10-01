from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from app.dispatch.intelligence import (
    ConstraintEvidence,
    ConstraintResult,
    DispatchRecommendation,
    EvidenceRef,
    EvidenceState,
    PlacementClass,
    PlacementRecommendation,
    TimeWindow,
)
from app.lia.dispatch_reasoning import (
    CallFact,
    CallReasoningContext,
    GhostSlotClass,
    ResolutionState,
    reason_about_dispatch,
)

NOW = datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc)
COMPANY = UUID("11111111-1111-4111-8111-111111111111")
BRANCH = UUID("22222222-2222-4222-8222-222222222222")
CONVERSATION = UUID("33333333-3333-4333-8333-333333333333")
EMPLOYEE = UUID("44444444-4444-4444-8444-444444444444")
POLICY = EvidenceRef("scheduling.urgency_policy", "drain-p1", "a" * 64)


def _fact(
    name: str,
    value: str | None = None,
    *,
    evidence: tuple[EvidenceRef, ...] = (),
) -> CallFact:
    return CallFact(
        name,
        value,
        ResolutionState.RESOLVED if value else ResolutionState.UNRESOLVED,
        "lia.call_interpretation",
        evidence,
    )


def _context(**changes: object) -> CallReasoningContext:
    base = CallReasoningContext(
        company_id=COMPANY,
        branch_id=BRANCH,
        conversation_id=CONVERSATION,
        revision=1,
        service_intent=_fact("SERVICE INTENT", "Drain Cleaning"),
        urgency=_fact("URGENCY", "Priority 1 / urgent same-day"),
        customer=_fact("CUSTOMER"),
        location=_fact("LOCATION"),
        membership=_fact("MEMBERSHIP"),
        availability_constraint=_fact("AVAILABILITY CONSTRAINT"),
        as_of=NOW,
        valid_until=NOW + timedelta(minutes=5),
    )
    return replace(base, **changes)


def _dispatch(*placements: PlacementRecommendation) -> DispatchRecommendation:
    evidence = (EvidenceRef("dispatch.runtime", "job-1", "b" * 64),)
    return DispatchRecommendation(
        recommendation_id=UUID("55555555-5555-4555-8555-555555555555"),
        contract_version="dispatch.recommendation.v1",
        engine_version="dispatch-deterministic-1",
        job_id=UUID("66666666-6666-4666-8666-666666666666"),
        company_id=COMPANY,
        branch_id=BRANCH,
        candidates=tuple(placements),
        risk_conditions=(),
        recovery_options=(),
        evidence=evidence,
        limitations=("Travel duration is unavailable and is not estimated.",),
        recommendation_digest="c" * 64,
    )


def _placement(
    *, rank: int | None, eligible: bool, result: ConstraintResult
) -> PlacementRecommendation:
    return PlacementRecommendation(
        employee_id=EMPLOYEE,
        proposed_window=TimeWindow(NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
        placement_class=PlacementClass.BEST_OVERALL_FIT,
        eligible=eligible,
        rank=rank,
        constraints=(
            ConstraintEvidence("employee_authority", result, "Employee authority is required."),
        ),
        tradeoffs=("Travel duration is unavailable and is not estimated.",),
        limitations=(),
        confidence=EvidenceState.KNOWN,
    )


def test_unresolved_caller_prompts_for_customer_and_address_without_policy_claim() -> None:
    result = reason_about_dispatch(_context(), None, evaluated_at=NOW)

    assert result.service_intent == "Drain Cleaning"
    assert result.urgency is None
    assert result.next_question == (
        "Are you a previous customer? May I have the service address?"
    )
    assert result.primary.slot_class is GhostSlotClass.UNAVAILABLE
    assert "configured policy evidence" in " ".join(result.limitations)
    assert "URGENCY: unresolved (configured policy evidence required)" in result.facts
    assert result.mutation_authority == "none"


def test_policy_backed_urgency_and_dispatch_evidence_produce_typed_ghost_slots() -> None:
    context = _context(
        urgency=_fact("URGENCY", "Priority 1 / urgent same-day", evidence=(POLICY,)),
        customer=_fact("CUSTOMER", "Existing Customer"),
        location=_fact("LOCATION", "Authoritative service location"),
    )
    result = reason_about_dispatch(
        context,
        _dispatch(
            _placement(rank=1, eligible=True, result=ConstraintResult.PASS),
            replace(_placement(rank=2, eligible=True, result=ConstraintResult.PASS), employee_id=UUID("77777777-7777-4777-8777-777777777777")),
            replace(_placement(rank=None, eligible=False, result=ConstraintResult.FAIL), employee_id=UUID("88888888-8888-4888-8888-888888888888")),
        ),
        evaluated_at=NOW,
    )

    assert result.urgency == "Priority 1 / urgent same-day"
    assert result.primary.slot_class is GhostSlotClass.PRIMARY_GHOST_SLOT
    assert [item.slot_class for item in result.alternates] == [
        GhostSlotClass.ALTERNATE_GHOST_SLOT,
        GhostSlotClass.CONSTRAINED_OPTION,
    ]
    assert "do not assign it automatically" in result.recommendation
    assert result.primary.evidence[0].authority == "dispatch.runtime"
    assert {item.authority for item in result.evidence} == {
        "dispatch.runtime",
        "scheduling.urgency_policy",
    }


def test_changed_call_facts_supersede_prior_reasoning_deterministically() -> None:
    first = reason_about_dispatch(_context(), None, evaluated_at=NOW)
    changed = _context(
        revision=2,
        customer=_fact("CUSTOMER", "Existing Customer"),
        location=_fact("LOCATION", "123 Main Street"),
    )
    second = reason_about_dispatch(changed, None, evaluated_at=NOW, prior=first)
    replay = reason_about_dispatch(changed, None, evaluated_at=NOW, prior=first)

    assert second.reasoning_id == replay.reasoning_id
    assert second.reasoning_digest == replay.reasoning_digest
    assert second.supersedes_reasoning_id == first.reasoning_id
    assert second.next_question == "Is there a time today when you cannot meet the technician?"


def test_expired_call_evidence_cannot_leave_a_stale_ghost_slot() -> None:
    result = reason_about_dispatch(
        _context(urgency=_fact("URGENCY", "Priority 1", evidence=(POLICY,))),
        _dispatch(_placement(rank=1, eligible=True, result=ConstraintResult.PASS)),
        evaluated_at=NOW + timedelta(minutes=6),
    )

    assert result.primary.slot_class is GhostSlotClass.UNAVAILABLE
    assert result.alternates == ()
    assert "evidence expired" in " ".join(result.limitations).lower()


def test_cross_scope_dispatch_evidence_fails_closed() -> None:
    foreign = replace(
        _dispatch(_placement(rank=1, eligible=True, result=ConstraintResult.PASS)),
        company_id=UUID("99999999-9999-4999-8999-999999999999"),
    )

    with pytest.raises(ValueError, match="does not match call scope"):
        reason_about_dispatch(_context(), foreign, evaluated_at=NOW)
