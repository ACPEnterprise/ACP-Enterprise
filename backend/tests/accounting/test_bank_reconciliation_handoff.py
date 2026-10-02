from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.accounting.banking import BankAuthorityService
from app.accounting.errors import AccountingConflict, AccountingNotFound
from app.main import app


def context(*, user_id=None, company_id=None):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id or uuid4()),
        company=SimpleNamespace(id=company_id or uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        active_branch=None,
    )


def reconciliation(*, actor, state="ready_to_submit", difference=Decimal(0)):
    return SimpleNamespace(
        id=uuid4(),
        company_id=actor.company.id,
        bank_account_id=uuid4(),
        preparer_user_id=actor.user.id,
        status=state,
        difference=difference,
        outstanding_items=[],
        version=1,
        submitted_at=None,
        reviewer_user_id=None,
        closed_at=None,
    )


@pytest.mark.asyncio
async def test_prepare_derives_authenticated_user_and_membership() -> None:
    actor = context()
    account_id = uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(
            side_effect=[SimpleNamespace(id=account_id), 0, None]
        ),
        flush=AsyncMock(),
        add=Mock(),
    )
    row = await BankAuthorityService().prepare_reconciliation(
        session,  # type: ignore[arg-type]
        context=actor,  # type: ignore[arg-type]
        bank_account_id=account_id,
        statement_identity="fixture-statement",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        ending_balance=Decimal("100.00"),
        book_balance=Decimal("100.00"),
        cleared_total=Decimal(0),
        outstanding_total=Decimal(0),
        cleared_transaction_ids=(),
        outstanding_items=[],
        source_evidence={"source_digest": "a" * 64},
    )
    assert row.preparer_user_id == actor.user.id
    assert row.preparer_membership_id == actor.membership.id
    assert row.status == "ready_to_submit"
    assert row.version == 1


@pytest.mark.asyncio
async def test_authenticated_preparer_submission_is_persisted_and_replay_safe() -> None:
    actor = context()
    row = reconciliation(actor=actor)
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=row), flush=AsyncMock(), add=Mock()
    )
    service = BankAuthorityService()
    result = await service.submit_reconciliation(
        session,  # type: ignore[arg-type]
        context=actor,  # type: ignore[arg-type]
        bank_account_id=row.bank_account_id,
        reconciliation_id=row.id,
        expected_version=1,
    )
    assert result.status == "submitted_for_review"
    assert result.version == 2
    assert result.submitted_at is not None
    replay = await service.submit_reconciliation(
        session,  # type: ignore[arg-type]
        context=actor,  # type: ignore[arg-type]
        bank_account_id=row.bank_account_id,
        reconciliation_id=row.id,
        expected_version=1,
    )
    assert replay is result


@pytest.mark.asyncio
async def test_submission_requires_zero_difference_and_no_blocker() -> None:
    actor = context()
    row = reconciliation(actor=actor, difference=Decimal("0.01"))
    session = SimpleNamespace(scalar=AsyncMock(return_value=row))
    with pytest.raises(AccountingConflict, match="zero difference"):
        await BankAuthorityService().submit_reconciliation(
            session,  # type: ignore[arg-type]
            context=actor,  # type: ignore[arg-type]
            bank_account_id=row.bank_account_id,
            reconciliation_id=row.id,
            expected_version=1,
        )
    row.difference = Decimal(0)
    row.outstanding_items = [{"state": "unresolved"}]
    with pytest.raises(AccountingConflict, match="blocking exceptions"):
        await BankAuthorityService().submit_reconciliation(
            session,  # type: ignore[arg-type]
            context=actor,  # type: ignore[arg-type]
            bank_account_id=row.bank_account_id,
            reconciliation_id=row.id,
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_distinct_authenticated_reviewer_closes_once_and_preparer_cannot() -> (
    None
):
    preparer = context()
    row = reconciliation(actor=preparer, state="submitted_for_review")
    row.submitted_at = datetime.now(timezone.utc)
    row.version = 2
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=row), flush=AsyncMock(), add=Mock()
    )
    with pytest.raises(AccountingConflict, match="self-close"):
        await BankAuthorityService().close_reconciliation(
            session,  # type: ignore[arg-type]
            context=preparer,  # type: ignore[arg-type]
            bank_account_id=row.bank_account_id,
            reconciliation_id=row.id,
            expected_version=2,
        )
    reviewer = context(company_id=preparer.company.id)
    closed = await BankAuthorityService().close_reconciliation(
        session,  # type: ignore[arg-type]
        context=reviewer,  # type: ignore[arg-type]
        bank_account_id=row.bank_account_id,
        reconciliation_id=row.id,
        expected_version=2,
    )
    assert closed.status == "closed"
    assert closed.reviewer_user_id == reviewer.user.id
    assert closed.version == 3
    assert closed.closed_at is not None
    replay = await BankAuthorityService().close_reconciliation(
        session,  # type: ignore[arg-type]
        context=context(company_id=preparer.company.id),  # type: ignore[arg-type]
        bank_account_id=row.bank_account_id,
        reconciliation_id=row.id,
        expected_version=2,
    )
    assert replay is closed


@pytest.mark.asyncio
async def test_stale_and_cross_company_reconciliation_are_rejected() -> None:
    actor = context()
    row = reconciliation(actor=actor, state="submitted_for_review")
    row.version = 2
    session = SimpleNamespace(scalar=AsyncMock(return_value=row))
    reviewer = context(company_id=actor.company.id)
    with pytest.raises(AccountingConflict, match="stale"):
        await BankAuthorityService().close_reconciliation(
            session,  # type: ignore[arg-type]
            context=reviewer,  # type: ignore[arg-type]
            bank_account_id=row.bank_account_id,
            reconciliation_id=row.id,
            expected_version=1,
        )
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(AccountingNotFound):
        await BankAuthorityService().close_reconciliation(
            session,  # type: ignore[arg-type]
            context=context(),  # type: ignore[arg-type]
            bank_account_id=row.bank_account_id,
            reconciliation_id=row.id,
            expected_version=2,
        )


def test_handoff_routes_require_auth_and_never_accept_actor_ids() -> None:
    paths = app.openapi()["paths"]
    prepare = (
        "/api/v1/accounting/banking/accounts/{bank_account_id}/reconciliations/prepare"
    )
    submit = (
        "/api/v1/accounting/banking/accounts/{bank_account_id}/reconciliations/"
        "{reconciliation_id}/submit"
    )
    close = (
        "/api/v1/accounting/banking/accounts/{bank_account_id}/reconciliations/"
        "{reconciliation_id}/close"
    )
    assert {prepare, submit, close} <= paths.keys()
    schemas = app.openapi()["components"]["schemas"]
    assert "preparer_user_id" not in schemas["BankReconciliationPrepare"]["properties"]
    assert set(schemas["BankReconciliationTransition"]["properties"]) == {
        "expected_version"
    }
    client = TestClient(app)
    for route in (prepare, submit, close):
        rendered = route.replace("{bank_account_id}", str(uuid4())).replace(
            "{reconciliation_id}", str(uuid4())
        )
        assert client.post(rendered, json={}).status_code == 401
