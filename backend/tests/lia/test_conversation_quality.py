from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.lia.contracts import LiaContext, LiaRequest, TruthClassification
from app.lia.conversation import (
    ActionRisk,
    CorrectionKind,
    ResponseMode,
    interpret_conversation,
)
from app.lia.planner import plan_question
from app.lia.retrieval import GovernedRetrievalService
from app.lia.service import LiaService


def _context(*permissions: str) -> SimpleNamespace:
    branch_id = uuid4()
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=uuid4()),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=4,
        has_permission=lambda permission: permission in permissions,
    )


@pytest.mark.parametrize(
    ("question", "mode"),
    (
        ("Short version.", ResponseMode.BRIEF),
        ("Just tell me what matters.", ResponseMode.BRIEF),
        ("Explain that.", ResponseMode.DETAILED),
        ("Walk me through it.", ResponseMode.DETAILED),
        ("Show me the evidence.", ResponseMode.EVIDENCE),
    ),
)
def test_response_mode_is_deterministic(question: str, mode: ResponseMode) -> None:
    assert interpret_conversation(question).response_mode is mode


@pytest.mark.parametrize(
    ("question", "kind", "subject"),
    (
        ("No, I meant Lianne.", CorrectionKind.SUBJECT, "Lianne"),
        ("Actually, show me Alex.", CorrectionKind.SUBJECT, "Alex"),
        ("No, I meant last month.", CorrectionKind.PERIOD, "last month"),
        ("Go back.", CorrectionKind.BACK, None),
        ("No, the other Smith.", CorrectionKind.AMBIGUOUS, None),
    ),
)
def test_correction_is_explicit(
    question: str, kind: CorrectionKind, subject: str | None
) -> None:
    result = interpret_conversation(question)
    assert result.correction is kind
    assert result.corrected_subject == subject


@pytest.mark.parametrize(
    ("question", "start", "end"),
    (
        ("today", date(2026, 9, 15), date(2026, 9, 15)),
        ("tomorrow", date(2026, 9, 16), date(2026, 9, 16)),
        ("last week", date(2026, 9, 7), date(2026, 9, 13)),
        ("last month", date(2026, 8, 1), date(2026, 8, 31)),
        ("May 2026", date(2026, 5, 1), date(2026, 5, 31)),
    ),
)
def test_temporal_language_resolves_before_retrieval(
    question: str, start: date, end: date
) -> None:
    period = interpret_conversation(question, today=date(2026, 9, 15)).period
    assert period is not None
    assert (period.starts_on, period.ends_on) == (start, end)


@pytest.mark.parametrize(
    ("question", "risk"),
    (
        ("Move this job to tomorrow", ActionRisk.SCHEDULING_CHANGE),
        ("Assign Jason to this job", ActionRisk.SCHEDULING_CHANGE),
        ("Send the estimate", ActionRisk.CUSTOMER_COMMUNICATION),
        ("Raise the price 5 percent", ActionRisk.PRICE_CHANGE),
        ("Approve payroll", ActionRisk.PAYROLL),
        ("Post the journal", ActionRisk.ACCOUNTING),
        ("Refund the customer", ActionRisk.MONEY_MOVEMENT),
        ("Grant her admin permission", ActionRisk.PERMISSION_CHANGE),
    ),
)
def test_action_requests_are_understood_without_execution(
    question: str, risk: ActionRisk
) -> None:
    action = interpret_conversation(question).action
    assert action is not None
    assert action.risk is risk


@pytest.mark.parametrize(
    ("question", "domain"),
    (
        ("How's business?", "beacon"),
        ("What's holding payroll up?", "payroll"),
        ("Why can't I see May numbers?", "accounting"),
        ("Who has the Smith job?", "dispatch"),
        ("What did we charge that customer last time?", "price-book"),
        ("Do we make money on drain cleaning?", "business-economics"),
        ("What's broken?", "launch-readiness"),
    ),
)
def test_owner_language_maps_only_to_bounded_domains(
    question: str, domain: str
) -> None:
    assert domain in plan_question(question).domains


def test_explicit_topic_switch_drops_prior_employee_domain() -> None:
    plan = plan_question(
        "Okay, what is scheduled tomorrow?",
        context_domain="workforce",
        topic_domains=("workforce", "payroll"),
    )
    assert plan.domains == frozenset({"scheduling"})


def test_named_back_reference_rebinds_subject_and_payroll_topic() -> None:
    plan = plan_question(
        "Back to Lianne — what does the accountant need for payroll?",
        context_domain="workforce",
        topic_domains=("scheduling",),
    )
    assert plan.subject_query == "Lianne"
    assert plan.domains == frozenset({"workforce", "payroll"})


@pytest.mark.asyncio
async def test_unbound_pronoun_requires_clarification_without_retrieval() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    result = await LiaService(retrieval=retrieval).ask(
        AsyncMock(), context=_context(), request=LiaRequest(question="Is she ready?")
    )
    assert result.classification is TruthClassification.INCOMPLETE
    retrieval.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_go_back_does_not_restore_unbounded_history() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    result = await LiaService(retrieval=retrieval).ask(
        AsyncMock(), context=_context(), request=LiaRequest(question="Go back")
    )
    assert result.classification is TruthClassification.INCOMPLETE
    assert "don't have an authorized earlier topic" in result.answer
    retrieval.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_intent_is_refused_and_navigable_without_mutation() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    result = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(),
        request=LiaRequest(
            question="Move this job to tomorrow",
            context=LiaContext(domain="jobs", entity_id=uuid4()),
        ),
    )
    assert result.classification is TruthClassification.POLICY_REQUIRED
    assert "scheduling change" in result.answer
    assert result.proposals == ()
    assert result.navigation[0].internal_path == "/scheduling"
    retrieval.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_capability_answer_reflects_read_only_boundary() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    result = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(),
        request=LiaRequest(question="Can you run payroll?"),
    )
    assert result.classification is TruthClassification.KNOWN
    assert "cannot" in result.answer
    assert result.proposals == ()
    retrieval.retrieve.assert_not_awaited()


QUESTION_FAMILIES = (
    "Show me the Customer history",
    "What happened on this Job",
    "What is scheduled tomorrow",
    "Who is assigned in Dispatch",
    "Show me Employee readiness",
    "What's holding Payroll up",
    "Why can't I see May financial reports",
    "What migration evidence is missing",
    "What does Luminary recommend",
    "What Beacon signal needs attention",
    "What Price Book review is open",
    "What is still blocking launch",
    "Move this job to tomorrow",
    "Show me the evidence for this invoice",
    "No, I meant Lianne",
)

SPEECH_VARIANTS = (
    "{}",
    "uh {}",
    "okay {}",
    "please {}",
    "{} please",
    "wait {}",
    "so {}",
    "hey LIA {}",
    "just {}",
    "can you {}",
    "I need to know: {}",
    "owner asked: {}",
    "quick question, {}",
    "right now, {}",
    "on screen, {}",
    "short version: {}",
    "explain: {}",
    "show me the evidence: {}",
    "from ACP, {}",
    "without changing anything, {}",
)


def test_conversation_acceptance_corpus_has_300_deterministic_cases() -> None:
    corpus = tuple(
        template.format(question)
        for question in QUESTION_FAMILIES
        for template in SPEECH_VARIANTS
    )
    assert len(corpus) == 300
    assert len(set(corpus)) == 300
    for transcript in corpus:
        result = interpret_conversation(transcript, today=date(2026, 9, 15))
        assert result.normalized
        plan = plan_question(transcript)
        assert (
            plan.domains
            or result.action is not None
            or result.correction is not CorrectionKind.NONE
            or result.response_mode is not ResponseMode.NORMAL
        )
