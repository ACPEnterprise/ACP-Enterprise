from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.beacon.history import EvaluationDisposition
from app.lia.contracts import (
    EvidenceReference,
    LiaContext,
    LiaRequest,
    LiaTemporalContext,
    TruthClassification,
)
from app.lia.owner_answers import compose_owner_answer
from app.lia.planner import QuestionIntent, plan_question
from app.lia.retrieval import GovernedRetrievalService
from app.lia.service import LiaService
from app.lia.temporal import resolve_temporal_context
from app.platform.permissions.codes import (
    AccountingPermission,
    AnalyticsPermission,
    SchedulingPermission,
)

ANCHOR = datetime(2026, 9, 15, 16, tzinfo=UTC)


def _context(*permissions: str) -> SimpleNamespace:
    branch_id = uuid4()
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=uuid4(), timezone="America/New_York"),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=8,
        has_permission=lambda permission: permission in permissions,
        can_access_branch=lambda candidate: candidate == branch_id,
    )


@pytest.mark.parametrize(
    ("question", "start", "end", "label"),
    (
        ("today", date(2026, 9, 15), date(2026, 9, 15), "today"),
        ("tomorrow", date(2026, 9, 16), date(2026, 9, 16), "tomorrow"),
        ("yesterday", date(2026, 9, 14), date(2026, 9, 14), "yesterday"),
        ("this week", date(2026, 9, 14), date(2026, 9, 20), "this week"),
        ("last week", date(2026, 9, 7), date(2026, 9, 13), "last week"),
        ("last month", date(2026, 8, 1), date(2026, 8, 31), "last month"),
        ("May 2026", date(2026, 5, 1), date(2026, 5, 31), "May 2026"),
        (
            "January through March 2026",
            date(2026, 1, 1),
            date(2026, 3, 31),
            "January 2026 through March 2026",
        ),
        (
            "2026-05-02 through 2026-05-12",
            date(2026, 5, 2),
            date(2026, 5, 12),
            "2026-05-02 through 2026-05-12",
        ),
        ("last year", date(2025, 1, 1), date(2025, 12, 31), "last year"),
    ),
)
def test_temporal_resolution_is_explicit(
    question: str, start: date, end: date, label: str
) -> None:
    result = resolve_temporal_context(
        question, timezone_name="America/New_York", now=ANCHOR
    )
    assert result is not None
    assert (result.start_date, result.end_date, result.period_label) == (
        start,
        end,
        label,
    )
    assert result.timezone == "America/New_York"


def test_comparison_preserves_both_explicit_periods() -> None:
    result = resolve_temporal_context(
        "Compare May and June 2026", timezone_name="America/New_York", now=ANCHOR
    )
    assert result is not None
    assert (result.start_date, result.end_date) == (
        date(2026, 5, 1),
        date(2026, 5, 31),
    )
    assert (result.comparison_start, result.comparison_end) == (
        date(2026, 6, 1),
        date(2026, 6, 30),
    )


def test_temporal_contract_rejects_inverted_ranges() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        LiaTemporalContext(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 5, 1),
            as_of=ANCHOR,
            timezone="UTC",
            period_label="invalid",
        )


@pytest.mark.asyncio
async def test_schedule_question_passes_period_to_authoritative_adapter() -> None:
    tomorrow = datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=1)
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        EvidenceReference(
            domain="scheduling",
            label="Appointments",
            authority="AUTHORITATIVE_FACT",
            observed_at=ANCHOR,
            freshness="CURRENT_QUERY",
            evidence_digest="a" * 64,
            count=2,
            state="scheduled=2",
            period_start=tomorrow,
            period_end=tomorrow,
            period_label="tomorrow",
            timezone="America/New_York",
        ),
    )
    result = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(SchedulingPermission.READ),
        request=LiaRequest(question="What's scheduled tomorrow?"),
    )
    temporal = retrieval.retrieve.await_args.kwargs["temporal"]
    assert temporal.start_date == tomorrow
    assert temporal.end_date == tomorrow
    assert result.temporal == temporal
    assert "tomorrow" in result.answer


@pytest.mark.asyncio
async def test_beacon_period_uses_company_branch_scoped_persisted_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(AnalyticsPermission.READ)
    temporal = LiaTemporalContext(
        start_date=date(2026, 9, 14),
        end_date=date(2026, 9, 15),
        as_of=ANCHOR,
        timezone="America/New_York",
        period_label="since yesterday",
    )
    record = SimpleNamespace(
        id=uuid4(),
        run_id=uuid4(),
        condition_key=uuid4(),
        evidence_digest="a" * 64,
        disposition=EvaluationDisposition.CHANGED,
        evaluated_at=ANCHOR - timedelta(hours=2),
        evidence_as_of=ANCHOR - timedelta(hours=2),
    )
    deltas = AsyncMock(return_value=(record,))
    completed = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.deltas", deltas
    )
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.has_completed_run",
        completed,
    )

    evidence = await GovernedRetrievalService._beacon_history(
        AsyncMock(), context, ANCHOR, temporal
    )

    assert evidence[0].authority == "AUTHORITATIVE_SIGNAL_HISTORY"
    assert evidence[0].source_contract_version == "BEACON.EVALUATION_HISTORY.v1"
    assert evidence[0].company_id == context.company.id
    assert evidence[0].branch_ids == (context.active_branch.id,)
    assert evidence[0].authorization_version == context.authorization_version
    assert evidence[0].period_start == temporal.start_date
    assert evidence[0].state == "changed=1"
    assert deltas.await_args.kwargs["company_id"] == context.company.id
    assert deltas.await_args.kwargs["branch_id"] == context.active_branch.id
    assert completed.await_args.kwargs["company_id"] == context.company.id


@pytest.mark.asyncio
async def test_beacon_completed_period_with_no_changes_is_authoritative_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(AnalyticsPermission.READ)
    temporal = LiaTemporalContext(
        start_date=date(2026, 9, 15),
        end_date=date(2026, 9, 15),
        as_of=ANCHOR,
        timezone="America/New_York",
        period_label="today",
    )
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.deltas",
        AsyncMock(return_value=()),
    )
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.has_completed_run",
        AsyncMock(return_value=True),
    )

    evidence = await GovernedRetrievalService._beacon_history(
        AsyncMock(), context, ANCHOR, temporal
    )

    assert evidence[0].count == 0
    assert evidence[0].freshness == "PERSISTED_EVIDENCE"
    assert evidence[0].state == "no Beacon changes recorded"


@pytest.mark.asyncio
async def test_beacon_period_without_completed_evaluation_is_explicitly_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(AnalyticsPermission.READ)
    temporal = LiaTemporalContext(
        start_date=date(2026, 9, 15),
        end_date=date(2026, 9, 15),
        as_of=ANCHOR,
        timezone="America/New_York",
        period_label="today",
    )
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.deltas",
        AsyncMock(return_value=()),
    )
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.has_completed_run",
        AsyncMock(return_value=False),
    )

    evidence = await GovernedRetrievalService._beacon_history(
        AsyncMock(), context, ANCHOR, temporal
    )

    assert evidence[0].authority == "PERIOD_AUTHORITY_UNAVAILABLE"
    assert evidence[0].freshness == "NO_ACCEPTED_EVIDENCE"
    assert evidence[0].limitations == (
        "no_completed_beacon_evaluation_in_period",
    )


@pytest.mark.asyncio
async def test_beacon_history_rejects_unbounded_period_before_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(AnalyticsPermission.READ)
    temporal = LiaTemporalContext(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        as_of=ANCHOR,
        timezone="America/New_York",
        period_label="January through March 2026",
    )
    deltas = AsyncMock()
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.deltas", deltas
    )

    evidence = await GovernedRetrievalService._beacon_history(
        AsyncMock(), context, ANCHOR, temporal
    )

    assert evidence[0].authority == "PERIOD_AUTHORITY_UNAVAILABLE"
    assert evidence[0].limitations == ("beacon_history_window_exceeds_31_days",)
    deltas.assert_not_awaited()


@pytest.mark.asyncio
async def test_beacon_period_history_is_not_queried_without_analytics_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    temporal = LiaTemporalContext(
        start_date=date(2026, 9, 15),
        end_date=date(2026, 9, 15),
        as_of=ANCHOR,
        timezone="America/New_York",
        period_label="today",
    )
    deltas = AsyncMock()
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_evaluation_history_service.deltas", deltas
    )

    evidence = await GovernedRetrievalService().retrieve(
        AsyncMock(), context=context, domains={"beacon"}, temporal=temporal
    )

    assert evidence == ()
    deltas.assert_not_awaited()


def test_beacon_period_answer_explains_why_without_fabricating_causality() -> None:
    evidence = EvidenceReference(
        domain="beacon",
        label="Beacon evaluation history",
        authority="AUTHORITATIVE_SIGNAL_HISTORY",
        observed_at=ANCHOR,
        freshness="PERSISTED_EVIDENCE",
        evidence_digest="f" * 64,
        count=5,
        state="changed=1, expired=1, new=2, resolved=1, still_active=0",
        period_start=date(2026, 9, 15),
        period_end=date(2026, 9, 15),
        period_label="today",
        timezone="America/New_York",
    )

    answer = compose_owner_answer("What changed in Beacon today?", (evidence,))

    assert "2 new, 1 changed, 1 resolved, and 1 expired" in answer.text
    assert "not an inferred timeline" in answer.text


def test_beacon_period_comparison_preserves_both_comparable_periods() -> None:
    may = EvidenceReference(
        domain="beacon",
        label="Beacon evaluation history",
        authority="AUTHORITATIVE_SIGNAL_HISTORY",
        observed_at=ANCHOR,
        freshness="PERSISTED_EVIDENCE",
        evidence_digest="a" * 64,
        count=2,
        state="changed=1, new=1",
        source_contract_version="BEACON.EVALUATION_HISTORY.v1",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        period_label="May 2026",
        timezone="America/New_York",
    )
    june = may.model_copy(
        update={
            "evidence_digest": "b" * 64,
            "state": "new=2, resolved=1",
            "count": 3,
            "period_start": date(2026, 6, 1),
            "period_end": date(2026, 6, 30),
            "period_label": "June 2026",
        }
    )

    answer = compose_owner_answer("Compare Beacon in May and June", (may, june))

    assert "May 2026: 1 new, 1 changed, 0 resolved, and 0 expired" in answer.text
    assert "June 2026: 2 new, 0 changed, 1 resolved, and 0 expired" in answer.text
    assert "do not establish business causality" in answer.text


@pytest.mark.asyncio
async def test_unsupported_history_never_retrieves_current_state() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        EvidenceReference(
            domain="jobs",
            label="Jobs",
            authority="PERIOD_AUTHORITY_UNAVAILABLE",
            observed_at=ANCHOR,
            freshness="NO_ACCEPTED_EVIDENCE",
            evidence_digest="b" * 64,
            count=0,
            state="period_unavailable=1",
            limitations=("authoritative_historical_filter_unavailable",),
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        ),
    )
    result = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context("COMPANY_JOB_READ"),
        request=LiaRequest(question="What Jobs did we complete last year?"),
    )
    assert result.classification is TruthClassification.INCOMPLETE
    assert "Current state was not presented as historical fact" in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "permission", "fragment"),
    (
        (
            "What invoices were still open at month end last month?",
            "COMPANY_INVOICE_READ",
            "historical Invoice-state snapshots",
        ),
        (
            "What needs scheduling today?",
            SchedulingPermission.READ,
            "no authoritative Appointment date",
        ),
    ),
)
async def test_unsupported_temporal_semantics_fail_before_retrieval(
    question: str, permission: str, fragment: str
) -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    result = await LiaService(retrieval=retrieval).ask(
        AsyncMock(), context=_context(permission), request=LiaRequest(question=question)
    )
    assert result.classification is TruthClassification.INCOMPLETE
    assert fragment in result.answer
    retrieval.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_comparison_retrieves_each_period_separately() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        EvidenceReference(
            domain="scheduling",
            label="Appointments",
            authority="AUTHORITATIVE_FACT",
            observed_at=ANCHOR,
            freshness="CURRENT_QUERY",
            evidence_digest="c" * 64,
            count=1,
            state="scheduled=1",
        ),
    )
    await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(SchedulingPermission.READ),
        request=LiaRequest(question="Compare the schedule in May and June 2026"),
    )
    assert retrieval.retrieve.await_count == 2
    first = retrieval.retrieve.await_args_list[0].kwargs["temporal"]
    second = retrieval.retrieve.await_args_list[1].kwargs["temporal"]
    assert (first.start_date, first.end_date) == (
        date(2026, 5, 1),
        date(2026, 5, 31),
    )
    assert (second.start_date, second.end_date) == (
        date(2026, 6, 1),
        date(2026, 6, 30),
    )


@pytest.mark.asyncio
async def test_comparison_answer_preserves_each_period_without_inventing_delta() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)

    async def period_evidence(*_args, **kwargs):
        temporal = kwargs["temporal"]
        is_may = temporal.start_date == date(2026, 5, 1)
        return (
            EvidenceReference(
                domain="scheduling",
                label="Appointments",
                authority="AUTHORITATIVE_FACT",
                observed_at=ANCHOR,
                freshness="CURRENT_QUERY",
                evidence_digest=("a" if is_may else "b") * 64,
                count=4 if is_may else 7,
                state="scheduled=4" if is_may else "scheduled=7",
                period_start=temporal.start_date,
                period_end=temporal.end_date,
                period_label=temporal.period_label,
                timezone=temporal.timezone,
            ),
        )

    retrieval.retrieve.side_effect = period_evidence
    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(SchedulingPermission.READ),
        request=LiaRequest(question="Compare the schedule in May and June 2026"),
    )

    assert "May 2026: Appointments — scheduled=4" in response.answer
    assert "June 2026: Appointments — scheduled=7" in response.answer
    assert "did not manufacture a difference" in response.answer


@pytest.mark.asyncio
async def test_financial_report_reuses_authoritative_engine_without_recalculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = SimpleNamespace(
        accounting_basis="accrual",
        currency="USD",
        generated_at=ANCHOR,
        checksum="e" * 64,
        definition_version="acc-rpt-1.0",
    )
    report = SimpleNamespace(
        manifest=manifest,
        quality=SimpleNamespace(freshness="current", integrity="passed"),
        revenue=(object(),),
        expenses=(object(),),
        total_revenue=Decimal("100.00"),
        total_expenses=Decimal("75.00"),
        net_income=Decimal("25.00"),
    )
    operation = AsyncMock(return_value=report)
    monkeypatch.setattr(
        "app.lia.retrieval.financial_reporting_service.income_statement", operation
    )
    temporal = LiaTemporalContext(
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        as_of=ANCHOR,
        timezone="America/New_York",
        period_label="May 2026",
    )
    context = _context(AccountingPermission.REPORT_READ)
    evidence = await GovernedRetrievalService._financial_report(
        AsyncMock(), context, ANCHOR, temporal, "accrual"
    )
    operation.assert_awaited_once()
    assert evidence.authority == "ACP_POSTED_LEDGER_AUTHORITY"
    assert "total revenue=100.00" in (evidence.state or "")
    assert evidence.accounting_basis == "accrual"


@pytest.mark.asyncio
async def test_financial_basis_mismatch_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = SimpleNamespace(
        manifest=SimpleNamespace(accounting_basis="accrual"),
    )
    monkeypatch.setattr(
        "app.lia.retrieval.financial_reporting_service.income_statement",
        AsyncMock(return_value=report),
    )
    temporal = LiaTemporalContext(
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        as_of=ANCHOR,
        timezone="America/New_York",
        period_label="May 2026",
    )
    evidence = await GovernedRetrievalService._financial_report(
        AsyncMock(),
        _context(AccountingPermission.REPORT_READ),
        ANCHOR,
        temporal,
        "cash",
    )
    assert evidence.authority == "PERIOD_AUTHORITY_UNAVAILABLE"
    assert "available_native_basis:accrual" in evidence.limitations


@pytest.mark.asyncio
async def test_follow_up_period_correction_preserves_prior_for_compare_them() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        EvidenceReference(
            domain="scheduling",
            label="Appointments",
            authority="AUTHORITATIVE_FACT",
            observed_at=ANCHOR,
            freshness="CURRENT_QUERY",
            evidence_digest="d" * 64,
            count=1,
            state="scheduled=1",
        ),
    )
    service = LiaService(retrieval=retrieval)
    context = _context(SchedulingPermission.READ)
    first = await service.ask(
        AsyncMock(),
        context=context,
        request=LiaRequest(question="Show me the schedule in May 2026"),
    )
    assert first.temporal is not None
    second = await service.ask(
        AsyncMock(),
        context=context,
        request=LiaRequest(
            question="What about June 2026?",
            conversation_id=first.conversation_id,
            context=LiaContext(
                domain="scheduling",
                authorization_version=first.authorization_version,
                topic_domains=("scheduling",),
                temporal=first.temporal,
            ),
        ),
    )
    assert second.temporal is not None
    assert second.temporal.prior_start == date(2026, 5, 1)
    before = retrieval.retrieve.await_count
    await service.ask(
        AsyncMock(),
        context=context,
        request=LiaRequest(
            question="Compare them",
            conversation_id=first.conversation_id,
            context=LiaContext(
                domain="scheduling",
                authorization_version=second.authorization_version,
                topic_domains=("scheduling",),
                temporal=second.temporal,
            ),
        ),
    )
    assert retrieval.retrieve.await_count == before + 2


TEMPORAL_QUESTIONS = (
    "What's scheduled today?",
    "What's scheduled tomorrow?",
    "What was scheduled yesterday?",
    "What's scheduled this week?",
    "How busy is Friday?",
    "Who is working tomorrow in Dispatch?",
    "What was unassigned yesterday?",
    "What Jobs did we complete in May?",
    "What work did we do for this Customer last year?",
    "How many Estimates did we write last month?",
    "What did we invoice in May?",
    "What invoices were paid last week?",
    "Show me May 2026 P&L",
    "Compare May and June financial reports",
    "What is blocking this pay period?",
    "How many timekeeping hours last week?",
    "How did drain cleaning perform last month?",
    "What became urgent in Beacon today?",
    "What changed in Migration this week?",
    "what's tomorrow look like",
)

TRANSCRIPT_VARIANTS = (
    "{}",
    "uh {}",
    "please {}",
    "owner asked {}",
    "show me {}",
    "what about {}",
    "no, I meant {}",
    "short version, {}",
    "voice transcript: {}",
    "without changing anything, {}",
)


def test_temporal_corpus_has_200_bounded_cases() -> None:
    corpus = tuple(
        variant.format(question)
        for question in TEMPORAL_QUESTIONS
        for variant in TRANSCRIPT_VARIANTS
    )
    assert len(corpus) == 200
    assert len(set(corpus)) == 200
    for question in corpus:
        plan = plan_question(question)
        temporal = resolve_temporal_context(
            question, timezone_name="America/New_York", now=ANCHOR
        )
        assert plan.intent is not QuestionIntent.UNSUPPORTED, question
        assert temporal is not None or "pay period" in question.casefold()
