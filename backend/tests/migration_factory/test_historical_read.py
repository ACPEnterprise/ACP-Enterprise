from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from app.migration_factory.historical_read import (
    AccountingReportEvidence,
    AccountingReportKind,
    AccountingReportReadRequest,
    CoverageDisposition,
    DomainCoverage,
    HistoricalAuthority,
    HistoricalDomain,
    HistoricalLineage,
    HistoricalReadPage,
    HistoricalReadRequest,
    HistoricalRecord,
)


def lineage(source_id: str) -> HistoricalLineage:
    return HistoricalLineage(
        "housecall_pro", source_id, "a" * 64, datetime.now(timezone.utc), None, "hcp/v1"
    )


def test_history_request_requires_explicit_bounded_range() -> None:
    with pytest.raises(ValueError, match="inverted"):
        HistoricalReadRequest(
            uuid4(), date(2026, 9, 1), date(2026, 8, 1), (HistoricalDomain.JOB,)
        )


def test_history_page_preserves_source_authority_and_partial_coverage() -> None:
    company_id = uuid4()
    customer_id = uuid4()
    record = HistoricalRecord(
        HistoricalDomain.PAYMENT,
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        None,
        customer_id,
        ("invoice:i1",),
        HistoricalAuthority.SOURCE_BACKED,
        {"amount": "25.00"},
        lineage("payment-1"),
        False,
    )
    page = HistoricalReadPage(
        "twelvehats-historical-read/v1",
        company_id,
        date(2026, 1, 1),
        date(2026, 8, 31),
        (record,),
        (
            DomainCoverage(
                HistoricalDomain.PAYMENT,
                CoverageDisposition.PARTIAL,
                4308,
                1,
                283,
                datetime.now(timezone.utc),
                "application tie-out unresolved",
            ),
        ),
        None,
        datetime.now(timezone.utc),
    )
    assert page.records[0].aggregation_safe is False
    assert page.coverage[0].disposition is CoverageDisposition.PARTIAL


def test_history_page_rejects_nondeterministic_order() -> None:
    older = HistoricalRecord(
        HistoricalDomain.JOB,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        None,
        None,
        (),
        HistoricalAuthority.SOURCE_BACKED,
        {},
        lineage("old"),
        False,
    )
    newer = HistoricalRecord(
        HistoricalDomain.JOB,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        None,
        None,
        (),
        HistoricalAuthority.SOURCE_BACKED,
        {},
        lineage("new"),
        False,
    )
    with pytest.raises(ValueError, match="newest-first"):
        HistoricalReadPage(
            "twelvehats-historical-read/v1",
            uuid4(),
            date(2025, 1, 1),
            date(2026, 1, 1),
            (older, newer),
            (),
            None,
            datetime.now(timezone.utc),
        )


def test_qbo_report_contract_never_silently_becomes_native() -> None:
    request = AccountingReportReadRequest(
        uuid4(),
        AccountingReportKind.GENERAL_LEDGER,
        date(2026, 1, 1),
        date(2026, 8, 31),
        "accrual",
    )
    with pytest.raises(ValueError, match="silently"):
        AccountingReportEvidence(
            "twelvehats-accounting-report-read/v1",
            request,
            "quickbooks_online",
            HistoricalAuthority.SOURCE_BACKED,
            "a" * 64,
            "b" * 64,
            None,
            {},
            True,
        )
