from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.accounting.close_controls import (
    AccountingCloseControlService,
    CanonicalReportEvidence,
    ComparisonState,
    ReportFamily,
    ReportLine,
    compare_reports,
)
from app.accounting.router import router

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
DIGEST = "a" * 64


def evidence(
    family: ReportFamily,
    *,
    authority: str,
    total: Decimal = Decimal(100),
    **changes: object,
) -> CanonicalReportEvidence:
    values: dict[str, object] = {
        "authority": authority,
        "available": True,
        "family": family,
        "legal_company_identity": "ALL_COUNTY_PLUMBING_AND_LEAK",
        "company_id": COMPANY_ID,
        "currency": "USD",
        "accounting_basis": "accrual",
        "start_date": date(2026, 5, 1),
        "end_date": date(2026, 5, 31),
        "cutoff": datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc),
        "timezone": "America/New_York",
        "parameters_digest": DIGEST,
        "report_version": "v1",
        "manifest_digest": DIGEST,
        "provenance": (f"{authority}:report",),
        "total": total,
        "total_debits": total if family is ReportFamily.TRIAL_BALANCE else None,
        "total_credits": total if family is ReportFamily.TRIAL_BALANCE else None,
        "lines": (
            ReportLine(
                identity="4000",
                label="Service revenue",
                amount=total,
                debit=Decimal(0),
                credit=total,
                classification="revenue",
                evidence_reference=f"{authority}:4000",
            ),
        ),
        "bucket_semantics_version": "aging-v1",
        "job_cost_semantics_version": "job-cost-v1",
    }
    values.update(changes)
    return CanonicalReportEvidence.model_validate(values)


@pytest.mark.parametrize("family", list(ReportFamily))
def test_all_report_families_compare_only_canonical_equivalent_evidence(
    family: ReportFamily,
) -> None:
    result = compare_reports(
        family,
        evidence(family, authority="ACP", total=Decimal("103.25")),
        evidence(family, authority="QBO", total=Decimal("100.00")),
    )

    assert result.state is ComparisonState.COMPARABLE
    assert result.difference == Decimal("3.25")
    assert result.lines[0].difference == Decimal("3.25")
    assert result.review_state == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"cutoff": datetime(2026, 6, 1, tzinfo=timezone.utc)}, "CUTOFF_MISMATCH"),
        ({"accounting_basis": "cash"}, "ACCOUNTING_BASIS_MISMATCH"),
        ({"currency": "CAD"}, "CURRENCY_MISMATCH"),
        ({"report_version": "v2"}, "SOURCE_REPORT_VERSION_MISMATCH"),
        ({"parameters_digest": "b" * 64}, "REPORT_PARAMETERS_MISMATCH"),
        (
            {"branch_id": UUID("22222222-2222-4222-8222-222222222222")},
            "BRANCH_SCOPE_MISMATCH",
        ),
    ],
)
def test_non_comparable_dimensions_never_produce_difference(
    change: dict[str, object], reason: str
) -> None:
    family = ReportFamily.PROFIT_AND_LOSS
    result = compare_reports(
        family,
        evidence(family, authority="ACP"),
        evidence(family, authority="QBO", **change),
    )

    assert result.state is ComparisonState.NOT_COMPARABLE
    assert reason in result.non_comparable_reasons
    assert result.difference is None
    assert result.lines == ()


def test_unavailable_evidence_is_not_coerced_to_zero() -> None:
    result = compare_reports(
        ReportFamily.CASH_FLOW,
        evidence(ReportFamily.CASH_FLOW, authority="ACP"),
        None,
    )

    assert result.state is ComparisonState.UNAVAILABLE
    assert result.qbo_total is None
    assert result.difference is None
    assert result.non_comparable_reasons == ("QBO_REPORT_UNAVAILABLE",)


def test_trial_balance_preserves_debit_credit_orientation() -> None:
    acp = evidence(ReportFamily.TRIAL_BALANCE, authority="ACP")
    qbo = evidence(ReportFamily.TRIAL_BALANCE, authority="QBO")

    result = compare_reports(ReportFamily.TRIAL_BALANCE, acp, qbo)

    line = result.lines[0]
    assert line.acp_debit == Decimal(0)
    assert line.acp_credit == Decimal(100)
    assert line.qbo_debit == Decimal(0)
    assert line.qbo_credit == Decimal(100)
    assert line.disposition == "MATCHED"
    assert result.acp_balanced is True
    assert result.qbo_balanced is True


def test_aging_and_job_cost_semantics_must_match() -> None:
    aging = compare_reports(
        ReportFamily.AR_AGING,
        evidence(ReportFamily.AR_AGING, authority="ACP"),
        evidence(
            ReportFamily.AR_AGING,
            authority="QBO",
            bucket_semantics_version="aging-v2",
        ),
    )
    costing = compare_reports(
        ReportFamily.JOB_COSTING,
        evidence(ReportFamily.JOB_COSTING, authority="ACP"),
        evidence(
            ReportFamily.JOB_COSTING,
            authority="QBO",
            job_cost_semantics_version="foreign-definition",
        ),
    )

    assert "AGING_BUCKET_SEMANTICS_MISMATCH" in aging.non_comparable_reasons
    assert "JOB_COST_SEMANTICS_MISMATCH" in costing.non_comparable_reasons


def test_operator_routes_are_read_only_server_owned_projections() -> None:
    methods = {
        route.path: route.methods
        for route in router.routes
        if getattr(route, "path", "").startswith("/api/v1/accounting")
    }

    assert methods["/api/v1/accounting/periods/{period_id}/report-comparisons"] == {
        "GET"
    }
    assert methods["/api/v1/accounting/accountant-review"] == {"GET"}
    assert methods["/api/v1/accounting/periods/{period_id}/close-readiness"] == {"GET"}


class MatchingReportProvider:
    async def evidence(self, session, *, context, family, period):
        del session, context, period
        return evidence(family, authority="ACP"), evidence(family, authority="QBO")


class ReadyPayrollProvider:
    async def readiness(self, session, *, context, period):
        del session, context, period
        return "READY", "payroll-control:digest"


@pytest.mark.asyncio
async def test_period_is_ready_only_from_complete_server_owned_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    period = SimpleNamespace(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        status="closing",
        version=4,
    )
    session = AsyncMock()
    empty = SimpleNamespace(all=list)
    session.scalars.side_effect = [empty, empty, empty, empty]
    session.scalar.return_value = SimpleNamespace(
        status="APPLIED", evidence_digest="c" * 64
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY_ID), can_access_branch=lambda _id: True
    )
    monkeypatch.setattr(
        "app.accounting.close_controls.financial_reporting_repository.context",
        AsyncMock(return_value=SimpleNamespace(currency="USD")),
    )
    service = AccountingCloseControlService(
        MatchingReportProvider(), ReadyPayrollProvider()
    )

    result = await service.readiness(session, context=context, period=period)

    assert result.overall_readiness == "READY"
    assert result.blockers == ()
    assert result.report_comparison_readiness == "READY"
    assert result.payroll_readiness == "READY"


@pytest.mark.asyncio
async def test_missing_server_evidence_remains_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    period = SimpleNamespace(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        status="closing",
        version=2,
    )
    session = AsyncMock()
    empty = SimpleNamespace(all=list)
    session.scalars.side_effect = [empty, empty, empty, empty]
    session.scalar.return_value = None
    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY_ID), can_access_branch=lambda _id: True
    )
    monkeypatch.setattr(
        "app.accounting.close_controls.financial_reporting_repository.context",
        AsyncMock(return_value=None),
    )

    result = await AccountingCloseControlService().readiness(
        session, context=context, period=period
    )

    assert result.overall_readiness == "BLOCKED"
    assert result.currency == "UNAVAILABLE"
    assert result.payroll_readiness == "UNAVAILABLE"
    assert {item.family for item in result.blockers} >= {
        "opening_equity",
        "payroll",
        "trial_balance",
        "profit_and_loss",
        "balance_sheet",
        "general_ledger",
        "ar_aging",
        "ap_aging",
        "cash_flow",
        "job_costing",
    }
