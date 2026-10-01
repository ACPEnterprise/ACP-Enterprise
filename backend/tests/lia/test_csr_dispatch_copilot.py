from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.lia.contracts import SpeechInterpretation
from app.lia.csr_dispatch_copilot import CustomerMatch, compose_csr_dispatch_copilot
from app.lia.dispatch_reasoning import GhostSlot, GhostSlotClass, LiaDispatchReasoning

NOW = datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc)
COMPANY = UUID("11111111-1111-4111-8111-111111111111")
BRANCH = UUID("22222222-2222-4222-8222-222222222222")
CONVERSATION = UUID("33333333-3333-4333-8333-333333333333")
CUSTOMER = UUID("44444444-4444-4444-8444-444444444444")
LOCATION = UUID("55555555-5555-4555-8555-555555555555")


def _reasoning() -> LiaDispatchReasoning:
    slot = GhostSlot(
        GhostSlotClass.PRIMARY_GHOST_SLOT,
        None,
        NOW,
        NOW,
        ("eligible",),
        ("canonical availability",),
        (),
        (),
    )
    return LiaDispatchReasoning(
        reasoning_id=UUID("66666666-6666-4666-8666-666666666666"),
        contract_version="v1",
        company_id=COMPANY,
        branch_id=BRANCH,
        conversation_id=CONVERSATION,
        revision=1,
        service_intent="Drain",
        urgency="routine",
        customer_state="RESOLVED",
        location_state="RESOLVED",
        next_question=None,
        facts=("SERVICE INTENT: Drain Cleaning", "LOCATION: canonical"),
        interpretation="Canonical Dispatch evidence supports an eligible option.",
        recommendation="Offer the primary slot for human review.",
        why=("Canonical availability is known.",),
        primary=slot,
        alternates=(),
        limitations=(),
        evidence=(),
        as_of=NOW,
        expires_at=NOW + timedelta(minutes=5),
        supersedes_reasoning_id=None,
        reasoning_digest="a" * 64,
    )


def _speech(*, state: str, confirmed: bool = False) -> SpeechInterpretation:
    return SpeechInterpretation(
        state=state,
        heard_text="water backs up",
        evidence_digest="b" * 64,
        possible_meaning="Water backs up into the tub.",
        suggested_confirmation="Please confirm that water backs up into the tub.",
        source_language="en",
        as_of=NOW,
        confirmed=confirmed,
        owning_fact_type="SERVICE_PROBLEM",
    )


def test_existing_customer_context_makes_recommendation_current() -> None:
    result = compose_csr_dispatch_copilot(
        _reasoning(),
        customer_match=CustomerMatch("EXISTING", CUSTOMER, LOCATION),
        evaluated_at=NOW,
    )
    assert result.customer_branch.state == "EXISTING"
    assert result.recommendation_state == "CURRENT"
    assert result.primary_ghost_slot is not None
    assert result.facts[0] == "SERVICE INTENT: Drain Cleaning"
    assert result.interpretation.startswith("Canonical Dispatch")
    assert result.as_of == NOW
    assert result.expires_at == NOW + timedelta(minutes=5)
    assert result.mutation_authority == "none"


def test_new_customer_requires_canonical_intake_and_keeps_recommendation_provisional() -> None:
    result = compose_csr_dispatch_copilot(
        _reasoning(),
        customer_match=CustomerMatch(
            "NEW_CUSTOMER_INTAKE_REQUIRED",
            missing_fields=("service_address",),
            next_questions=("What is the service address?",),
        ),
        evaluated_at=NOW,
    )
    assert result.customer_branch.state == "NEW_CUSTOMER_INTAKE_REQUIRED"
    assert result.recommendation_state == "PROVISIONAL"
    assert result.suggested_question == "What is the service address?"


def test_unconfirmed_speech_is_clarification_and_not_canonical_fact() -> None:
    result = compose_csr_dispatch_copilot(
        _reasoning(),
        customer_match=CustomerMatch("EXISTING", CUSTOMER, LOCATION),
        evaluated_at=NOW,
        speech=(_speech(state="CONFIRM_RECOMMENDED"),),
    )
    assert result.clarification_required is True
    assert result.suggested_question.startswith("Please confirm")
    assert result.recommendation_state == "PROVISIONAL"


def test_confirmed_non_confident_speech_is_rejected() -> None:
    try:
        compose_csr_dispatch_copilot(
            _reasoning(),
            customer_match=CustomerMatch("EXISTING", CUSTOMER, LOCATION),
            evaluated_at=NOW,
            speech=(_speech(state="UNCERTAIN", confirmed=True),),
        )
    except ValueError as error:
        assert "CONFIDENT" in str(error)
    else:
        raise AssertionError("unconfirmed speech must not enter canonical authority")


def test_ambiguous_customer_never_becomes_current_and_asks_disambiguation() -> None:
    result = compose_csr_dispatch_copilot(
        _reasoning(),
        customer_match=CustomerMatch(
            "AMBIGUOUS",
            next_questions=("Which service address is this for?",),
            limitations=("Multiple canonical Customer/Location matches exist.",),
        ),
        evaluated_at=NOW,
    )

    assert result.customer_branch.state == "AMBIGUOUS"
    assert result.recommendation_state == "PROVISIONAL"
    assert result.suggested_question == "Which service address is this for?"
    assert result.primary_ghost_slot is not None
    assert "provisional" in " ".join(result.limitations).lower()


def test_expired_reasoning_removes_every_ghost_slot() -> None:
    result = compose_csr_dispatch_copilot(
        _reasoning(),
        customer_match=CustomerMatch("EXISTING", CUSTOMER, LOCATION),
        evaluated_at=NOW + timedelta(minutes=5),
    )

    assert result.recommendation_state == "EXPIRED"
    assert result.primary_ghost_slot is None
    assert result.alternates == ()
    assert result.constrained_options == ()
    assert "refresh" in " ".join(result.limitations).lower()


@pytest.mark.parametrize(
    "fact_type",
    ("SERVICE_ADDRESS", "CALLER_NAME", "SERVICE_SYMPTOM", "URGENCY"),
)
def test_low_confidence_critical_speech_requires_confirmation(
    fact_type: str,
) -> None:
    uncertain = _speech(state="UNCERTAIN").model_copy(
        update={"owning_fact_type": fact_type}
    )
    result = compose_csr_dispatch_copilot(
        _reasoning(),
        customer_match=CustomerMatch("EXISTING", CUSTOMER, LOCATION),
        evaluated_at=NOW,
        speech=(uncertain,),
    )

    assert result.clarification_required is True
    assert result.recommendation_state == "PROVISIONAL"
    assert result.suggested_question == (
        "Please confirm that water backs up into the tub."
    )
