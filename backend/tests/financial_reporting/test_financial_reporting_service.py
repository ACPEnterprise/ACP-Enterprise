from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.financial_reporting.errors import (
    ReportingIntegrityError,
    ReportingNotFound,
    ReportingRequestError,
)
from app.financial_reporting.repository import (
    LedgerLineFact,
    PeriodFact,
    ReportingContextFact,
)
from app.financial_reporting.service import FinancialReportingService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission


class FakeRepository:
    def __init__(
        self,
        report_context: ReportingContextFact,
        period: PeriodFact,
        lines: tuple[LedgerLineFact, ...],
    ) -> None:
        self.report_context = report_context
        self.period_fact = period
        self.lines = lines

    async def context(self, _session: object, company_id: UUID):
        return self.report_context if company_id == self.report_context.company_id else None

    async def period(self, _session: object, company_id: UUID, period_id: UUID):
        if company_id == self.report_context.company_id and period_id == self.period_fact.id:
            return self.period_fact
        return None

    async def ledger_lines(
        self,
        _session: object,
        *,
        company_id: UUID,
        as_of: date,
        branch_id: UUID | None,
    ):
        return tuple(
            line
            for line in self.lines
            if line.company_id == company_id
            and line.effective_date <= as_of
            and (branch_id is None or line.branch_id == branch_id)
        )


def _context(company_id: UUID, branch_id: UUID) -> AuthorizationContext:
    return cast(
        AuthorizationContext,
        SimpleNamespace(
            company=SimpleNamespace(id=company_id),
            user=SimpleNamespace(id=uuid4()),
            has_permission=lambda code: code == AccountingPermission.REPORT_READ,
            can_access_branch=lambda candidate: candidate == branch_id,
        ),
    )


def _line(
    *,
    company_id: UUID,
    branch_id: UUID,
    journal_id: UUID,
    ordinal: int,
    account_id: UUID,
    code: str,
    classification: str,
    normal_balance: str,
    effective_date: date,
    debit: Decimal = Decimal(0),
    credit: Decimal = Decimal(0),
    journal_total: Decimal,
) -> LedgerLineFact:
    return LedgerLineFact(
        line_id=uuid4(),
        journal_id=journal_id,
        ordinal=ordinal,
        company_id=company_id,
        branch_id=branch_id,
        account_id=account_id,
        account_code=code,
        account_name=f"Account {code}",
        classification=classification,
        normal_balance=normal_balance,
        account_status="active",
        account_effective_from=date(2026, 1, 1),
        account_effective_to=None,
        period_id=PERIOD_ID,
        period_name="2026",
        period_start_date=date(2026, 1, 1),
        period_end_date=date(2026, 12, 31),
        period_status="open",
        journal_type="automated",
        journal_status="posted",
        effective_date=effective_date,
        currency="USD",
        journal_description="Posted source fact",
        line_description=f"Line {ordinal}",
        debit=debit,
        credit=credit,
        journal_total_debits=journal_total,
        journal_total_credits=journal_total,
        prepared_by_user_id=uuid4(),
        approved_by_user_id=uuid4(),
        posted_at=datetime(2026, 8, ordinal, tzinfo=timezone.utc),
        source_system="acp_enterprise",
        source_type="test_fact",
        source_identity=str(journal_id),
        source_digest=journal_id.hex * 2,
        posting_rule_version="test-v1",
        correlation_id=uuid4(),
        reversal_of_id=None,
        journal_version=4,
    )


PERIOD_ID = uuid4()


def _runtime():
    company_id, branch_id = uuid4(), uuid4()
    accounts = {
        "cash": uuid4(),
        "receivable": uuid4(),
        "revenue": uuid4(),
        "expense": uuid4(),
    }
    sale, receipt, expense = uuid4(), uuid4(), uuid4()
    lines = (
        _line(company_id=company_id, branch_id=branch_id, journal_id=sale, ordinal=1, account_id=accounts["receivable"], code="1100", classification="asset", normal_balance="debit", effective_date=date(2026, 1, 15), debit=Decimal(100), journal_total=Decimal(100)),
        _line(company_id=company_id, branch_id=branch_id, journal_id=sale, ordinal=2, account_id=accounts["revenue"], code="4000", classification="revenue", normal_balance="credit", effective_date=date(2026, 1, 15), credit=Decimal(100), journal_total=Decimal(100)),
        _line(company_id=company_id, branch_id=branch_id, journal_id=receipt, ordinal=1, account_id=accounts["cash"], code="1000", classification="asset", normal_balance="debit", effective_date=date(2026, 2, 1), debit=Decimal(40), journal_total=Decimal(40)),
        _line(company_id=company_id, branch_id=branch_id, journal_id=receipt, ordinal=2, account_id=accounts["receivable"], code="1100", classification="asset", normal_balance="debit", effective_date=date(2026, 2, 1), credit=Decimal(40), journal_total=Decimal(40)),
        _line(company_id=company_id, branch_id=branch_id, journal_id=expense, ordinal=1, account_id=accounts["expense"], code="5000", classification="expense", normal_balance="debit", effective_date=date(2026, 2, 2), debit=Decimal(20), journal_total=Decimal(20)),
        _line(company_id=company_id, branch_id=branch_id, journal_id=expense, ordinal=2, account_id=accounts["cash"], code="1000", classification="asset", normal_balance="debit", effective_date=date(2026, 2, 2), credit=Decimal(20), journal_total=Decimal(20)),
    )
    report_context = ReportingContextFact(company_id, "America/New_York", "USD", "accrual", 1)
    period = PeriodFact(PERIOD_ID, "2026", date(2026, 1, 1), date(2026, 12, 31), "open", 1)
    repository = FakeRepository(report_context, period, lines)
    service = FinancialReportingService(cast(Any, repository))
    return service, repository, _context(company_id, branch_id), branch_id, accounts


@pytest.mark.asyncio
async def test_statements_reconcile_exactly_to_posted_ledger() -> None:
    service, _, context, _, _ = _runtime()
    trial = await service.trial_balance(cast(Any, object()), context=context, as_of=date(2026, 12, 31))
    assert trial.total_debits == trial.total_credits == Decimal(160)
    assert trial.total_ending_balance == 0
    balance_sheet = await service.balance_sheet(cast(Any, object()), context=context, as_of=date(2026, 12, 31))
    assert balance_sheet.total_assets == Decimal(80)
    assert balance_sheet.current_earnings == Decimal(80)
    assert balance_sheet.total_assets == balance_sheet.liabilities_equity_and_current_earnings
    income = await service.income_statement(cast(Any, object()), context=context, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    assert income.total_revenue == Decimal(100)
    assert income.total_expenses == Decimal(20)
    assert income.net_income == Decimal(80)


@pytest.mark.asyncio
async def test_general_ledger_is_stable_and_ties_to_account_balance() -> None:
    service, _, context, _, accounts = _runtime()
    result = await service.general_ledger(cast(Any, object()), context=context, start_date=date(2026, 2, 1), end_date=date(2026, 12, 31), account_id=accounts["receivable"])
    assert result.beginning_balance == Decimal(100)
    assert result.total_credits == Decimal(40)
    assert result.ending_balance == Decimal(60)
    assert result.rows[-1].running_balance == Decimal(60)


@pytest.mark.asyncio
async def test_manifest_checksum_is_reproducible_for_same_cutoff() -> None:
    service, _, context, _, _ = _runtime()
    first = await service.trial_balance(cast(Any, object()), context=context, as_of=date(2026, 12, 31))
    second = await service.trial_balance(cast(Any, object()), context=context, as_of=date(2026, 12, 31))
    assert first.manifest.ledger_cutoff == second.manifest.ledger_cutoff
    assert first.manifest.checksum == second.manifest.checksum


@pytest.mark.asyncio
async def test_company_branch_period_and_permission_scope_fail_closed() -> None:
    service, _, context, _, _ = _runtime()
    with pytest.raises(ReportingNotFound, match="Branch"):
        await service.trial_balance(cast(Any, object()), context=context, as_of=date(2026, 12, 31), branch_id=uuid4())
    with pytest.raises(ReportingRequestError, match="boundaries"):
        await service.income_statement(cast(Any, object()), context=context, start_date=date(2026, 2, 1), end_date=date(2026, 12, 31), period_id=PERIOD_ID)
    denied = cast(Any, context)
    denied.has_permission = lambda _code: False
    with pytest.raises(ReportingNotFound):
        await service.trial_balance(cast(Any, object()), context=denied, as_of=date(2026, 12, 31))


@pytest.mark.asyncio
async def test_invalid_posting_and_contradictory_evidence_fail_closed() -> None:
    service, repository, context, _, _ = _runtime()
    repository.lines = (replace(repository.lines[0], journal_total_credits=Decimal(99)), *repository.lines[1:])
    with pytest.raises(ReportingIntegrityError, match="journal_balance"):
        await service.trial_balance(cast(Any, object()), context=context, as_of=date(2026, 12, 31))
