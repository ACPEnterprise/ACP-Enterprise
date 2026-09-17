from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.lia.owner_answers import compose_owner_answer
from app.lia.retrieval import GovernedRetrievalService


def _context() -> SimpleNamespace:
    branch_id = uuid4()
    return SimpleNamespace(
        company=SimpleNamespace(id=uuid4()),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=12,
    )


def _signal(signal_id):
    return SimpleNamespace(
        id=signal_id,
        evidence_digest="a" * 64,
        title="Three completed Jobs still need Invoice review",
        severity=SimpleNamespace(value="warning"),
        priority=SimpleNamespace(
            band=SimpleNamespace(value="high"),
            explanation="Completed work remains outside the Invoice workflow.",
        ),
        recommended_action="Review the completed Jobs and their Invoice readiness.",
    )


@pytest.mark.asyncio
async def test_exact_beacon_context_explains_only_selected_signal(monkeypatch) -> None:
    selected_id = uuid4()
    other_id = uuid4()
    queue = SimpleNamespace(
        active=(_signal(selected_id), _signal(other_id)),
        snoozed=(),
    )
    query = AsyncMock(return_value=queue)
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_query_service.get_attention_queue", query
    )

    evidence = await GovernedRetrievalService._beacon(
        AsyncMock(),
        _context(),
        datetime(2026, 9, 17, 12, tzinfo=UTC),
        entity_id=selected_id,
    )

    assert len(evidence) == 1
    assert evidence[0].entity_id == selected_id
    assert evidence[0].authority == "BEACON.INTELLIGENCE.v1"
    assert "Completed work remains outside" in evidence[0].state
    answer = compose_owner_answer("Why did Beacon flag this?", evidence)
    assert "Three completed Jobs" in answer.text
    assert "did not infer a cause" in answer.text


@pytest.mark.asyncio
async def test_unknown_beacon_context_hides_existence(monkeypatch) -> None:
    queue = SimpleNamespace(active=(_signal(uuid4()),), snoozed=())
    monkeypatch.setattr(
        "app.lia.retrieval.beacon_query_service.get_attention_queue",
        AsyncMock(return_value=queue),
    )

    evidence = await GovernedRetrievalService._beacon(
        AsyncMock(),
        _context(),
        datetime(2026, 9, 17, 12, tzinfo=UTC),
        entity_id=uuid4(),
    )

    assert evidence == ()
