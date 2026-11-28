import os
from datetime import date
from pathlib import Path

import pytest
from app.qbo_source.historical_archive import (
    HistoricalReport,
    historical_archive_catalog,
    historical_payroll_records,
    historical_report,
    search_historical_archive,
    transaction_type_counts,
)

ARCHIVE = Path(os.environ.get("QBO_MANUAL_ARCHIVE_TEST_ROOT", "/unavailable"))


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_catalog_accounts_for_every_custody_dataset_and_disclosed_exception() -> None:
    catalog = historical_archive_catalog(root=ARCHIVE)
    counts = {item["key"]: item["record_count"] for item in catalog["datasets"]}

    assert len(catalog["datasets"]) == 21
    assert counts["accounts"] == 131
    assert counts["customers"] == 909
    assert counts["vendors"] == 868
    assert counts["invoices"] == 1341
    assert counts["general_ledger"] == 46405
    assert counts["account_detail"] == 46410
    assert counts["paychecks"] == 709
    assert catalog["source_record_count"] == 20702
    assert catalog["relationship_identity_count"] == 97093
    assert catalog["exception_count"] == 7
    assert catalog["mutation_authority"] == "none"


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_search_preserves_record_level_identity_and_date_filters() -> None:
    result = search_historical_archive(
        root=ARCHIVE,
        kind="invoice",
        query=None,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 11, 19),
        transaction_type="Invoice",
        account=None,
        offset=0,
        limit=5,
    )

    assert result["total"] > 0
    assert len(result["records"]) == 5
    assert all(len(item["source_identity"]) == 64 for item in result["records"])
    assert all(
        item["identity_kind"] == "custody-file-sha256-plus-report-row"
        for item in result["records"]
    )
    assert result["mutation_authority"] == "none"


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_general_ledger_control_and_cash_activity_are_complete() -> None:
    counts = transaction_type_counts(root=ARCHIVE)
    report = historical_report(
        root=ARCHIVE,
        report="general_ledger",
        start_date=None,
        end_date=None,
    )

    assert sum(counts.values()) == 46405
    assert counts["Invoice"] == 3140
    assert counts["Payment"] == 2469
    assert counts["Expense"] == 14370
    assert counts["Payroll Check"] == 5762
    assert report["record_count"] == 46405
    assert report["amount_total"] == "7496709.24"
    assert report["mutation_authority"] == "none"


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
@pytest.mark.parametrize(
    "report_name", ["profit_and_loss", "balance_sheet", "trial_balance"]
)
def test_sealed_financial_statements_retain_source_period_and_digest(
    report_name: HistoricalReport,
) -> None:
    report = historical_report(
        root=ARCHIVE,
        report=report_name,
        start_date=None,
        end_date=None,
    )

    assert report["record_count"] > 0
    assert len(report["source_sha256"]) == 64
    assert report["source_mode"] == "sealed_source_report"
    assert report["mutation_authority"] == "none"


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_historical_payroll_is_read_only_and_searchable() -> None:
    result = historical_payroll_records(root=ARCHIVE, query=None, offset=0, limit=5)

    assert result["total"] == 709
    assert len(result["records"]) == 5
    assert result["mutation_authority"] == "none"
    assert "no_payroll_execution_authority" in result["limitations"]
