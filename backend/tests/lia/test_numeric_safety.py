from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.lia.contracts import EvidenceReference, LiaRequest, TruthClassification
from app.lia.retrieval import GovernedRetrievalService
from app.lia.service import LiaService


def _context() -> SimpleNamespace:
    branch_id = uuid4()
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=uuid4(), timezone="America/New_York"),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=11,
        has_permission=lambda _permission: True,
        can_access_branch=lambda candidate: candidate == branch_id,
    )


def _evidence(domain: str, *, authority: str, state: str) -> EvidenceReference:
    return EvidenceReference(
        domain=domain,
        label=domain.replace("-", " ").title(),
        authority=authority,
        observed_at=datetime(2026, 9, 17, 12, tzinfo=UTC),
        freshness="CURRENT_QUERY",
        evidence_digest=(domain[0] if domain else "a") * 64,
        count=3,
        state=state,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "domain", "state"),
    (
        ("How much did we invoice in May?", "invoicing", "open=2, paid=1"),
        ("How much did we collect in May?", "payments", "payments=3"),
        ("How much is owed to us?", "accounting", "reporting_ready=1"),
    ),
)
async def test_amount_questions_never_turn_record_counts_into_dollars(
    question: str, domain: str, state: str
) -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        _evidence(domain, authority="AUTHORITATIVE_FACT", state=state),
    )

    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(), context=_context(), request=LiaRequest(question=question)
    )

    assert response.classification is TruthClassification.INCOMPLETE
    assert "does not provide the authoritative monetary aggregate" in response.answer
    assert "Record counts were not presented as dollars." in response.limitations
    assert all("$3" not in value for value in (response.answer, *response.limitations))


@pytest.mark.asyncio
async def test_posted_ledger_amount_evidence_is_not_blocked() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        _evidence(
            "accounting",
            authority="ACP_POSTED_LEDGER_AUTHORITY",
            state="report=P&L, amount=125000.00, basis=ACCRUAL",
        ),
    )

    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(),
        request=LiaRequest(question="How much revenue did we have in May 2026?"),
    )

    assert response.classification is not TruthClassification.INCOMPLETE
    assert (
        "does not provide the authoritative monetary aggregate" not in response.answer
    )
