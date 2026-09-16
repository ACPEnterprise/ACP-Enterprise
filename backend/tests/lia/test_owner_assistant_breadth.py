from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.lia.acceptance_corpus import (
    OWNER_QUESTION_CORPUS,
    Usefulness,
    corpus_totals,
)
from app.lia.contracts import EvidenceReference, LiaRequest
from app.lia.owner_answers import compose_owner_answer
from app.lia.planner import QuestionIntent, plan_question
from app.lia.retrieval import GovernedRetrievalService
from app.lia.service import LiaService


def _evidence(
    domain: str,
    state: str,
    *,
    count: int = 1,
    authority: str = "AUTHORITATIVE_FACT",
) -> EvidenceReference:
    return EvidenceReference(
        domain=domain,
        label=domain.replace("-", " ").title(),
        authority=authority,
        observed_at=datetime.now(timezone.utc),
        freshness="CURRENT_QUERY",
        evidence_digest=(domain[0] if domain else "a") * 64,
        count=count,
        state=state,
    )


def test_owner_acceptance_corpus_is_broad_and_has_no_accepted_failures() -> None:
    totals = corpus_totals()
    assert len(OWNER_QUESTION_CORPUS) == 112
    assert len({case.case_id for case in OWNER_QUESTION_CORPUS}) == 112
    assert len({case.family for case in OWNER_QUESTION_CORPUS}) == 14
    assert totals == {
        Usefulness.USEFUL_PASS: 104,
        Usefulness.SAFE_BUT_NOT_USEFUL: 8,
        Usefulness.FAIL: 0,
    }
    assert all(
        case.dependency
        for case in OWNER_QUESTION_CORPUS
        if case.expected is Usefulness.SAFE_BUT_NOT_USEFUL
    )


def test_every_useful_standalone_question_routes_to_bounded_sources() -> None:
    follow_up_families = {"customer", "job"}
    for case in OWNER_QUESTION_CORPUS:
        if case.expected is not Usefulness.USEFUL_PASS:
            continue
        plan = plan_question(
            case.question,
            context_domain=(
                "customers"
                if case.family == "customer"
                else "jobs"
                if case.family == "job"
                else None
            ),
            topic_domains=() if case.family not in follow_up_families else (case.family,),
        )
        assert plan.intent is not QuestionIntent.UNSUPPORTED, case.case_id
        assert plan.domains, case.case_id


@pytest.mark.parametrize(
    ("question", "evidence", "expected"),
    (
        (
            "What needs my attention?",
            (_evidence("beacon", "active=3, snoozed=1", count=4),),
            "3 active conditions",
        ),
        (
            "What do we know about profitability?",
            (
                _evidence(
                    "business-economics",
                    "complete=2, partial=1",
                    count=3,
                    authority="AUTHORITATIVE_MEASUREMENT",
                ),
            ),
            "3 admitted profitability",
        ),
        (
            "How much HCP history do we have?",
            (
                _evidence(
                    "migration",
                    "qualified=2, held=1",
                    count=3,
                    authority="AUTHORITATIVE_MIGRATION_EVIDENCE",
                ),
            ),
            "operational availability are separate",
        ),
        (
            "Show me the May 2026 P&L",
            (_evidence("accounting", "open=1", count=1),),
            "will not manufacture",
        ),
        (
            "What is scheduled today?",
            (_evidence("scheduling", "scheduled=7", count=7),),
            "7",
        ),
        (
            "What can I actually use today?",
            (_evidence("launch-readiness", "blocking=4, closed=2", count=6),),
            "end-to-end usable",
        ),
    ),
)
def test_question_families_render_owner_friendly_conclusions(
    question: str, evidence: tuple[EvidenceReference, ...], expected: str
) -> None:
    answer = compose_owner_answer(question, evidence)
    assert expected in answer.text
    assert "Here is the current authorized ACP evidence" not in answer.text
    assert answer.next_action.startswith("Open ")


def test_contextual_safe_summary_is_preserved_without_inventing_fields() -> None:
    employee_id = uuid4()
    evidence = EvidenceReference(
        domain="workforce",
        label="Minimum-necessary Workforce readiness context",
        authority="WORKFORCE.LIA_CONTEXT.v1",
        observed_at=datetime.now(timezone.utc),
        freshness="CURRENT_QUERY",
        entity_id=employee_id,
        evidence_digest="a" * 64,
        count=2,
        state="Employee Sample Employee is active; Mobile readiness READY",
        limitations=("compensation_payroll_tax_and_banking_are_excluded",),
    )
    answer = compose_owner_answer("Is this Employee mobile ready?", (evidence,))
    assert "Mobile readiness READY" in answer.text
    assert "bank" not in answer.text.casefold()


@pytest.mark.asyncio
async def test_service_uses_owner_answer_and_remains_read_only() -> None:
    branch_id = uuid4()
    context = type(
        "Context",
        (),
        {
            "user": type("User", (), {"id": uuid4()})(),
            "company": type("Company", (), {"id": uuid4()})(),
            "membership": type("Membership", (), {"id": uuid4()})(),
            "active_branch": type("Branch", (), {"id": branch_id})(),
            "authorized_branch_ids": frozenset({branch_id}),
            "authorization_version": 1,
            "has_permission": lambda _self, _permission: True,
        },
    )()
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        _evidence("beacon", "active=2, snoozed=0", count=2),
    )
    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=context,
        request=LiaRequest(question="What are the active Beacon issues?"),
    )
    assert "2 active conditions" in response.answer
    assert response.safe_next_action == "Open Beacon attention"
    assert response.proposals == ()


def test_breadth_changes_add_no_mutation_primitive() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "lia"
    for path in (root / "owner_answers.py", root / "acceptance_corpus.py"):
        source = path.read_text()
        for forbidden in (
            "session.add(",
            "session.delete(",
            "session.commit(",
            "schedule_appointment",
            "post_journal",
            "execute_payment",
        ):
            assert forbidden not in source
