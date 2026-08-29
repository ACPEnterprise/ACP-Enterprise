from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.payroll.paystatement_experience import DeterministicPayStatementRenderer
from app.payroll.reporting import (
    FilingConfigurationAuthority,
    HistoryCoverageEvidence,
    PayrollReportingEngine,
    PayrollReportingSource,
    ReportingError,
    ReportingPeriod,
    ReportingPeriodKind,
    ReportingState,
    prepare_filing_package,
)


def digest(character: str) -> str:
    return character * 64


def source(
    *,
    company_id=None,
    employee_id=None,
    identity="source-1",
    effective=date(2026, 1, 15),
    currency="USD",
    active=True,
    approved=True,
    off_cycle=False,
) -> PayrollReportingSource:
    return PayrollReportingSource(
        source_id=identity,
        source_digest=digest(identity[-1] if identity[-1] in "abcdef" else "a"),
        company_id=company_id or COMPANY,
        employee_id=employee_id or EMPLOYEE,
        period_id=uuid4(),
        effective_date=effective,
        currency=currency,
        gross=Decimal("1000.00"),
        employee_taxes=Decimal("150.00"),
        employer_taxes_contributions=Decimal("90.00"),
        employee_deductions=Decimal("50.00"),
        net_pay=Decimal("800.00"),
        approved=approved,
        active=active,
        off_cycle=off_cycle,
    )


COMPANY, EMPLOYEE = uuid4(), uuid4()
PERIOD = ReportingPeriod(
    "2026-Q1", ReportingPeriodKind.QUARTER, date(2026, 1, 1), date(2026, 3, 31)
)
COVERAGE = HistoryCoverageEvidence(
    "coverage-2026",
    digest("b"),
    COMPANY,
    date(2026, 1, 1),
    date(2026, 12, 31),
    True,
    True,
    "native_acp_history",
)


def test_authoritative_qtd_reconciles_and_replays() -> None:
    engine = PayrollReportingEngine()
    values = (
        source(),
        source(identity="source-c", effective=date(2026, 2, 15), off_cycle=True),
    )
    first = engine.compose(
        company_id=COMPANY, period=PERIOD, sources=values, coverage=COVERAGE
    )
    replay = engine.compose(
        company_id=COMPANY,
        period=PERIOD,
        sources=tuple(reversed(values)),
        coverage=COVERAGE,
    )
    assert first == replay and first.state is ReportingState.AUTHORITATIVE
    assert (
        first.totals
        and first.totals.gross == Decimal("2000.00")
        and first.totals.net_pay == Decimal("1600.00")
    )


def test_incomplete_history_is_partial_and_cannot_file() -> None:
    result = PayrollReportingEngine().compose(
        company_id=COMPANY, period=PERIOD, sources=(source(),), coverage=None
    )
    assert (
        result.state is ReportingState.PARTIAL
        and "HISTORY_INCOMPLETE" in result.blockers
    )
    with pytest.raises(ReportingError, match="authoritative"):
        prepare_filing_package(
            result=result,
            authority=FilingConfigurationAuthority(
                "config",
                digest("c"),
                COMPANY,
                "synthetic",
                "quarterly",
                "test-v1",
                PERIOD.start,
                None,
                True,
                True,
            ),
        )


def test_superseded_and_cross_currency_fail_closed() -> None:
    superseded = PayrollReportingEngine().compose(
        company_id=COMPANY,
        period=PERIOD,
        sources=(source(active=False),),
        coverage=COVERAGE,
    )
    assert superseded.state is ReportingState.CONFLICTING
    currency = PayrollReportingEngine().compose(
        company_id=COMPANY,
        period=PERIOD,
        sources=(source(), source(identity="source-d", currency="CAD")),
        coverage=COVERAGE,
    )
    assert currency.state is ReportingState.CONFLICTING


def test_company_and_source_reconciliation_are_enforced() -> None:
    with pytest.raises(ReportingError, match="cross-Company"):
        PayrollReportingEngine().compose(
            company_id=COMPANY,
            period=PERIOD,
            sources=(source(company_id=uuid4()),),
            coverage=COVERAGE,
        )
    with pytest.raises(ReportingError, match="reconcile"):
        PayrollReportingSource(
            source_id="bad",
            source_digest=digest("d"),
            company_id=COMPANY,
            employee_id=EMPLOYEE,
            period_id=uuid4(),
            effective_date=PERIOD.start,
            currency="USD",
            gross=Decimal(100),
            employee_taxes=Decimal(10),
            employer_taxes_contributions=Decimal(5),
            employee_deductions=Decimal(5),
            net_pay=Decimal(90),
            approved=True,
            active=True,
        )


def test_provider_neutral_filing_package_is_evidence_not_submission() -> None:
    result = PayrollReportingEngine().compose(
        company_id=COMPANY, period=PERIOD, sources=(source(),), coverage=COVERAGE
    )
    authority = FilingConfigurationAuthority(
        "synthetic-quarter-v1",
        digest("e"),
        COMPANY,
        "synthetic-jurisdiction",
        "quarterly-employer-report",
        "synthetic-schema-v1",
        PERIOD.start,
        None,
        True,
        True,
    )
    package = prepare_filing_package(result=result, authority=authority)
    assert package.state == "prepared_not_submitted"
    assert (
        package.package_id
        == prepare_filing_package(result=result, authority=authority).package_id
    )


def test_authoritative_ytd_renders_and_incomplete_history_stays_unavailable() -> None:
    content = {
        "period_start": "2026-01-10",
        "period_end": "2026-01-16",
        "earnings": [],
        "gross_pay": "1000.00",
        "employee_taxes": "150.00",
        "employee_deductions": "50.00",
        "net_pay": "800.00",
        "payment_method": "paper_check",
    }
    base = {
        "id": uuid4(),
        "lifecycle": "issued",
        "supersedes_statement_id": None,
        "statement_version": 2,
        "currency": "USD",
        "payment_status": "pending",
        "statement_digest": digest("f"),
    }
    authoritative = SimpleNamespace(
        **base,
        ytd_status="authoritative",
        content={**content, "ytd": {"gross": "3000.00", "net_pay": "2400.00"}},
    )
    rendered = DeterministicPayStatementRenderer().render(
        authoritative,
        company_name="Synthetic Company",
        employee_name="Synthetic Employee",
    )
    assert b"Year to date" in rendered and b"3000.00" in rendered
    unavailable = SimpleNamespace(**base, ytd_status="unavailable", content=content)
    fallback = DeterministicPayStatementRenderer().render(
        unavailable,
        company_name="Synthetic Company",
        employee_name="Synthetic Employee",
    )
    assert b"Year-to-date totals are unavailable" in fallback
