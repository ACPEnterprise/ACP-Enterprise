from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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


@pytest.mark.asyncio
async def test_import_preview_is_non_mutating_and_classifies_new_replay_conflict() -> None:
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
    confirm = BankImportConfirmRequest(
        **request.model_dump(), preview_digest="0" * 64
    )
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


def test_operator_routes_are_default_deny_and_expose_no_reopen_or_money_movement() -> None:
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
        response = getattr(client, method)(path.replace("{bank_account_id}", str(uuid4())))
        assert response.status_code in {401, 422}
    banking_paths = tuple(path for path in paths if "/accounting/banking" in path)
    assert not any("reopen" in path or "move-money" in path for path in banking_paths)
