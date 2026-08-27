from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.posting.contracts import (
    PostingFact,
    PostingLeg,
    PostingOutcome,
    PostingRule,
    PostingSide,
)
from app.accounting.posting.rules import PostingRuleRegistry
from app.accounting.posting.service import AutomatedPostingService
from app.accounting.service import AccountingService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission


def _context(company_id, branch_id, permission):
    return cast(
        AuthorizationContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4()),
            company=SimpleNamespace(id=company_id),
            can_access_branch=lambda candidate: candidate == branch_id,
            has_permission=lambda candidate: candidate == permission,
        ),
    )


def _runtime():
    company_id, branch_id = uuid4(), uuid4()
    rule = PostingRule(
        company_id=company_id,
        event_type="payment.receipt_captured",
        version="cash-receipt-v1",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        approved_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
        approved_by_user_id=uuid4(),
        legs=(
            PostingLeg("cash", uuid4(), PostingSide.DEBIT, "Undeposited funds"),
            PostingLeg("cash", uuid4(), PostingSide.CREDIT, "Accounts receivable"),
        ),
    )
    fact = PostingFact(
        schema_version="1.0",
        company_id=company_id,
        branch_id=branch_id,
        source_event_id=uuid4(),
        source_type="payment_receipt",
        source_id=uuid4(),
        event_type=rule.event_type,
        effective_date=date(2026, 8, 27),
        occurred_at=datetime(2026, 8, 27, 10, tzinfo=timezone.utc),
        currency="USD",
        components={"cash": Decimal("40.00")},
        evidence_digest="a" * 64,
    )
    accounting = cast(Any, AsyncMock(spec=AccountingService))
    created = SimpleNamespace(id=uuid4(), status="draft", version=1, posted_at=None)
    prepared = SimpleNamespace(**{**created.__dict__, "status": "prepared", "version": 2})
    approved = SimpleNamespace(**{**created.__dict__, "status": "approved", "version": 3})
    posted_at = datetime.now(timezone.utc)
    posted = SimpleNamespace(**{**created.__dict__, "status": "posted", "version": 4, "posted_at": posted_at})
    accounting.create_journal.return_value = created
    accounting.prepare_journal.return_value = prepared
    accounting.approve_journal.return_value = approved
    accounting.post_journal.return_value = posted
    service = AutomatedPostingService(rules=PostingRuleRegistry((rule,)), accounting=accounting)
    contexts = (
        _context(company_id, branch_id, AccountingPermission.JOURNAL_PREPARE),
        _context(company_id, branch_id, AccountingPermission.FINANCE_APPROVE),
        _context(company_id, branch_id, AccountingPermission.JOURNAL_POST),
    )
    return service, accounting, fact, contexts


@pytest.mark.asyncio
async def test_posts_balanced_journal_through_governed_core_lifecycle() -> None:
    service, accounting, fact, contexts = _runtime()
    sink = SimpleNamespace(deliver=AsyncMock())
    receipt = await service.post(
        cast(Any, object()),
        fact=fact,
        period_id=uuid4(),
        preparer=contexts[0],
        approver=contexts[1],
        poster=contexts[2],
        receipt_sink=sink,
    )
    assert receipt.status is PostingOutcome.POSTED
    data = accounting.create_journal.call_args.kwargs["data"]
    assert data.source_digest == fact.canonical_digest()
    assert sum(line.debit for line in data.lines) == sum(line.credit for line in data.lines) == Decimal("40.00")
    sink.deliver.assert_awaited_once_with(receipt)


@pytest.mark.asyncio
async def test_replay_resumes_without_repeating_completed_transitions() -> None:
    service, accounting, fact, contexts = _runtime()
    accounting.create_journal.return_value = accounting.post_journal.return_value
    await service.post(
        cast(Any, object()), fact=fact, period_id=uuid4(), preparer=contexts[0], approver=contexts[1], poster=contexts[2]
    )
    accounting.prepare_journal.assert_not_awaited()
    accounting.approve_journal.assert_not_awaited()
    accounting.post_journal.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_branch_permission_and_sod_fail_closed() -> None:
    service, accounting, fact, contexts = _runtime()
    bad_poster = _context(fact.company_id, fact.branch_id, AccountingPermission.READ)
    with pytest.raises(AccountingValidation, match="permission"):
        await service.post(cast(Any, object()), fact=fact, period_id=uuid4(), preparer=contexts[0], approver=contexts[1], poster=bad_poster)
    same_actor = cast(Any, contexts[2])
    same_actor.user.id = contexts[0].user.id
    with pytest.raises(AccountingConflict, match="distinct"):
        await service.post(cast(Any, object()), fact=fact, period_id=uuid4(), preparer=contexts[0], approver=contexts[1], poster=same_actor)
    accounting.create_journal.assert_not_awaited()


def test_unknown_or_extra_components_never_become_zero() -> None:
    service, _, fact, _ = _runtime()
    changed = replace(
        fact, components={"cash": Decimal(40), "fee": Decimal(1)}
    )
    with pytest.raises(AccountingValidation, match="every fact component"):
        service._journal_create(changed, service.rules.resolve(changed), uuid4())
