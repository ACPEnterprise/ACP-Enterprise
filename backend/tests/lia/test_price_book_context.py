from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from uuid import uuid4

import pytest

from app.lia.owner_answers import compose_owner_answer
from app.lia.planner import plan_question
from app.lia.price_book_context import (
    CONTRACT_VERSION,
    PriceBookLiaContextService,
)
from app.platform.permissions.codes import PriceBookPermission


def _context(*, permitted: bool = True, active_branch: bool = True):
    branch = SimpleNamespace(id=uuid4()) if active_branch else None
    return SimpleNamespace(
        company=SimpleNamespace(id=uuid4()),
        active_branch=branch,
        authorization_version=7,
        has_permission=lambda permission: permitted
        and permission == PriceBookPermission.READ,
    )


def _catalog(*, duplicate: bool = False, current: bool = True):
    item_id = uuid4()
    version_id = uuid4()
    items = [
        SimpleNamespace(
            id=item_id,
            code="DRAIN-100",
            name="Drain Cleaning",
            current_version_id=version_id if current else None,
        )
    ]
    if duplicate:
        items.append(
            SimpleNamespace(
                id=uuid4(),
                code="DRAIN-200",
                name="Drain Cleaning",
                current_version_id=uuid4(),
            )
        )
    versions = (
        SimpleNamespace(
            id=version_id,
            status="active",
            currency="USD",
            unit_price=Decimal("185.00"),
            effective_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        ),
    )
    return SimpleNamespace(service_items=tuple(items), versions=versions)


def test_price_question_plans_an_exact_price_book_subject() -> None:
    plan = plan_question("What's our price for drain cleaning?")
    assert plan.subject_domain == "price-book"
    assert plan.subject_query == "drain cleaning"
    assert plan.domains == frozenset({"price-book"})


@pytest.mark.asyncio
async def test_exact_branch_scoped_price_uses_authoritative_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = AsyncMock(return_value=_catalog())
    monkeypatch.setattr(
        "app.lia.price_book_context.price_book_service.catalog", catalog
    )
    context = _context()

    result = await PriceBookLiaContextService().resolve_exact(
        AsyncMock(), context=context, query="  DRAIN cleaning "
    )

    assert len(result.matches) == 1
    assert result.evidence is not None
    assert result.evidence.authority == CONTRACT_VERSION
    assert result.evidence.state == (
        "CURRENT_PRICE|Drain Cleaning (DRAIN-100) is USD 185.00 effective 2026-09-01."
    )
    assert "cost" not in result.evidence.state.casefold()
    assert "margin" not in result.evidence.state.casefold()
    catalog.assert_awaited_once_with(
        ANY,
        context=context,
        branch_id=context.active_branch.id,
        search="  DRAIN cleaning ",
        item_status="active",
        limit=25,
    )
    answer = compose_owner_answer("What's our price?", (result.evidence,))
    assert "USD 185.00" in answer.text
    assert "cost and margin evidence are not included" in answer.text


@pytest.mark.asyncio
async def test_price_lookup_never_guesses_or_bypasses_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = AsyncMock(return_value=_catalog(duplicate=True))
    monkeypatch.setattr(
        "app.lia.price_book_context.price_book_service.catalog", catalog
    )
    ambiguous = await PriceBookLiaContextService().resolve_exact(
        AsyncMock(), context=_context(), query="Drain Cleaning"
    )
    assert len(ambiguous.matches) == 2
    assert ambiguous.evidence is None

    no_branch = await PriceBookLiaContextService().resolve_exact(
        AsyncMock(), context=_context(active_branch=False), query="Drain Cleaning"
    )
    assert no_branch.branch_required

    denied = await PriceBookLiaContextService().resolve_exact(
        AsyncMock(), context=_context(permitted=False), query="Drain Cleaning"
    )
    assert denied.matches == ()
    assert catalog.await_count == 1
