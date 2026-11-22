from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.accounting.banking_operator import BankingOperatorService
from app.accounting.banking_schemas import (
    BankImportConfirmRequest,
    BankImportPreviewRequest,
    BankTransactionIngest,
    CashFlowResponse,
    CashFlowSection,
)
from app.accounting.errors import AccountingConflict
from app.main import app
from fastapi.testclient import TestClient

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


class Rows:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


def transaction(identity: str, digest: str = "a" * 64) -> BankTransactionIngest:
    return BankTransactionIngest(
        source_system="fixture-bank",
        external_transaction_id=identity,
        source_version="v1",
        source_digest=digest,
        acquired_at=NOW,
        source_as_of=NOW,
        posted_date=date(2026, 10, 1),
        effective_date=date(2026, 10, 1),
        amount=Decimal("25.00"),
        currency="USD",
        direction="inflow",
        kind="deposit",
        description="Sanitized fixture",
    )


def preview_request(*items: BankTransactionIngest) -> BankImportPreviewRequest:
    return BankImportPreviewRequest(
        statement_identity="fixture-statement",
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        opening_balance=Decimal("100.00"),
        ending_balance=Decimal("125.00"),
        transactions=items,
    )


def bank_account(
    company_id: UUID, institution_name: str, account_name: str
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        company_id=company_id,
        ledger_account_id=uuid4(),
        institution_name=institution_name,
        account_name=account_name,
        account_type="checking",
        masked_identity="•••• 1234",
        currency="USD",
        status="active",
        source_system="synthetic-statement",
        source_account_id=str(uuid4()),
        source_version="v1",
        source_digest="f" * 64,
        source_as_of=NOW,
        opening_balance=None,
        opening_balance_date=None,
    )


@pytest.mark.asyncio
async def test_bank_feed_health_is_configured_and_company_isolated() -> None:
    company_id, other_company_id = uuid4(), uuid4()
    capital_one = bank_account(company_id, "Capital One", "Operating")
    chase = bank_account(company_id, "Chase", "Corporate card")
    chase_empty = bank_account(company_id, "Chase", "New account")
    stale_transaction = SimpleNamespace(
        id=uuid4(), source_as_of=datetime(2026, 8, 30, tzinfo=timezone.utc)
    )
    current_transaction = SimpleNamespace(
        id=uuid4(), source_as_of=datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    )
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                Rows([capital_one, chase, chase_empty]),
                Rows([stale_transaction]),
                Rows([]),
                Rows([current_transaction]),
                Rows([]),
                Rows([]),
                Rows([]),
            ]
        ),
        scalar=AsyncMock(return_value=None),
    )

    result = await BankingOperatorService(
        stale_after_hours=48, clock=lambda: NOW
    ).summaries(session, company_id=company_id)  # type: ignore[arg-type]

    by_name = {row.account.account_name: row for row in result}
    assert by_name["Operating"].feed_health == "STALE"
    assert by_name["Operating"].latest_source_as_of == datetime(
        2026, 8, 30, tzinfo=timezone.utc
    )
    assert by_name["Operating"].stale_since == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert by_name["Operating"].source_age_hours == 792
    assert by_name["Corporate card"].feed_health == "CURRENT"
    assert by_name["Corporate card"].source_age_hours == 12
    assert by_name["Corporate card"].stale_since is None
    assert by_name["New account"].feed_health == "NO_EVIDENCE"
    assert by_name["New account"].latest_source_as_of is None
    assert all(row.stale_after_hours == 48 for row in result)

    statements = [call.args[0] for call in session.scalars.await_args_list]
    statements.extend(call.args[0] for call in session.scalar.await_args_list)
    for statement in statements:
        values = tuple(statement.compile().params.values())
        assert company_id in values
        assert other_company_id not in values


@pytest.mark.asyncio
async def test_import_preview_is_non_mutating_and_classifies_new_replay_conflict() -> (
    None
):
    company_id, account_id = uuid4(), uuid4()
    account = SimpleNamespace(id=account_id, company_id=company_id)
    existing = [
        SimpleNamespace(
            source_system="fixture-bank",
            external_transaction_id="replay",
            source_digest="b" * 64,
        ),
        SimpleNamespace(
            source_system="fixture-bank",
            external_transaction_id="conflict",
            source_digest="c" * 64,
        ),
    ]
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=account),
        scalars=AsyncMock(return_value=Rows(existing)),
        add=AsyncMock(),
    )
    request = preview_request(
        transaction("new"),
        transaction("replay", "b" * 64),
        transaction("conflict", "d" * 64),
    )
    result = await BankingOperatorService().preview_import(
        session,  # type: ignore[arg-type]
        company_id=company_id,
        account_id=account_id,
        request=request,
    )
    assert (result.new_count, result.replay_count, result.conflict_count) == (1, 1, 1)
    assert len(result.preview_digest) == 64
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_import_preview_detects_batch_duplicates() -> None:
    company_id, account_id = uuid4(), uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(id=account_id)),
        scalars=AsyncMock(return_value=Rows([])),
    )
    result = await BankingOperatorService().preview_import(
        session,  # type: ignore[arg-type]
        company_id=company_id,
        account_id=account_id,
        request=preview_request(transaction("same"), transaction("same")),
    )
    assert result.duplicate_count == 2
    assert result.new_count == 0


@pytest.mark.asyncio
async def test_confirm_requires_exact_preview_digest() -> None:
    company_id, account_id = uuid4(), uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(id=account_id)),
        scalars=AsyncMock(return_value=Rows([])),
    )
    request = preview_request(transaction("new"))
    confirm = BankImportConfirmRequest(**request.model_dump(), preview_digest="0" * 64)
    context = SimpleNamespace(company=SimpleNamespace(id=company_id))
    with pytest.raises(AccountingConflict, match="changed"):
        await BankingOperatorService().confirm_import(
            session,  # type: ignore[arg-type]
            context=context,  # type: ignore[arg-type]
            account_id=account_id,
            request=confirm,
        )


def test_cash_flow_contract_preserves_tie_and_incomplete_truth() -> None:
    tied = CashFlowResponse(
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        basis="posted_cash_movement",
        cutoff=date(2026, 10, 31),
        completeness="COMPLETE",
        beginning_cash=Decimal(100),
        operating_activities=CashFlowSection(amount=Decimal(25), journal_ids=()),
        investing_activities=CashFlowSection(amount=Decimal(0), journal_ids=()),
        financing_activities=CashFlowSection(amount=Decimal(0), journal_ids=()),
        unclassified_amount=Decimal(0),
        unclassified_journal_ids=(),
        net_change=Decimal(25),
        ending_cash=Decimal(125),
        canonical_bank_cash=Decimal(125),
        difference=Decimal(0),
        tie_status="TIED",
    )
    assert tied.beginning_cash + tied.net_change == tied.ending_cash
    partial = tied.model_copy(
        update={
            "completeness": "PARTIAL",
            "canonical_bank_cash": None,
            "difference": None,
            "tie_status": "UNAVAILABLE",
        }
    )
    assert partial.tie_status == "UNAVAILABLE"


def test_operator_routes_are_default_deny_and_expose_no_reopen_or_money_movement() -> (
    None
):
    client = TestClient(app)
    paths = app.openapi()["paths"]
    required = {
        "/api/v1/accounting/banking/summary",
        "/api/v1/accounting/banking/accounts/{bank_account_id}/imports/preview",
        "/api/v1/accounting/banking/accounts/{bank_account_id}/imports/confirm",
        "/api/v1/accounting/banking/match-review",
        "/api/v1/accounting/banking/accounts/{bank_account_id}/reconciliations/preview",
        "/api/v1/accounting/banking/accounts/{bank_account_id}/reconciliations/history",
        "/api/v1/accounting/banking/cash-flow",
    }
    assert required <= paths.keys()
    for path in required:
        method = "post" if "preview" in path or "confirm" in path else "get"
        response = getattr(client, method)(
            path.replace("{bank_account_id}", str(uuid4()))
        )
        assert response.status_code in {401, 422}
    banking_paths = tuple(path for path in paths if "/accounting/banking" in path)
    assert not any("reopen" in path or "move-money" in path for path in banking_paths)
