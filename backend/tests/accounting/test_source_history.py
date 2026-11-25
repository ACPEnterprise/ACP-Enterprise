from datetime import date
from decimal import Decimal

from app.accounting.source_history import (
    FinancialHistoryDisposition,
    FinancialReportDisposition,
    FinancialReportSourceRecord,
    FinancialSourceRecord,
    project_financial_history,
    project_financial_reports,
)


def record(
    source_type: str,
    source_id: str,
    *relationships: str,
    digest: str = "a" * 64,
) -> FinancialSourceRecord:
    return FinancialSourceRecord(
        source_type,
        source_id,
        date(2026, 1, 1),
        Decimal("125.00"),
        "USD",
        relationships,
        {"source_status": "synthetic"},
        digest,
    )


def test_source_backed_financial_relationships_are_deterministic_and_read_only() -> (
    None
):
    rows = (
        record("Customer", "c1"),
        record("Invoice", "i1", "Customer:c1"),
        record("Payment", "p1", "Invoice:i1"),
    )
    first = project_financial_history("quickbooks_online", rows)
    second = project_financial_history("quickbooks_online", reversed(rows))
    assert first == second
    assert first.read_only is True
    assert all(item.accepted_as_native is False for item in first.items)


def test_missing_relationship_remains_an_explicit_exception() -> None:
    result = project_financial_history(
        "quickbooks_online", (record("Payment", "p1", "Invoice:missing"),)
    )
    item = result.items[0]
    assert item.disposition is FinancialHistoryDisposition.HELD_MISSING_RELATIONSHIP
    assert item.source_payload is None
    assert item.related_source_keys == ("Invoice:missing",)


def test_exact_replay_converges_and_changed_source_evidence_is_held() -> None:
    invoice = record("Invoice", "i1")
    exact = project_financial_history("quickbooks_online", (invoice, invoice))
    assert len(exact.items) == 1
    conflict = project_financial_history(
        "quickbooks_online", (invoice, record("Invoice", "i1", digest="b" * 64))
    )
    assert conflict.items[0].disposition is FinancialHistoryDisposition.HELD_CONFLICT
    assert conflict.items[0].source_payload is None


def test_relationship_namespace_must_match_exactly() -> None:
    result = project_financial_history(
        "quickbooks_online",
        (
            record("Customer", "shared"),
            record("Payment", "p1", "Invoice:shared"),
        ),
    )
    payment = next(item for item in result.items if item.source_key == "Payment:p1")
    assert payment.disposition is FinancialHistoryDisposition.HELD_MISSING_RELATIONSHIP


def report(
    *account_totals: tuple[str, str],
    total: str,
    digest: str = "c" * 64,
) -> FinancialReportSourceRecord:
    return FinancialReportSourceRecord(
        "profit_and_loss",
        "r1",
        date(2026, 1, 1),
        date(2026, 1, 31),
        "accrual",
        "USD",
        tuple((key, Decimal(amount)) for key, amount in account_totals),
        Decimal(total),
        digest,
    )


def test_report_readback_agrees_with_source_backed_relationship_totals() -> None:
    history = project_financial_history(
        "quickbooks_online",
        (
            record("Account", "income", digest="a" * 64),
            record("Account", "expense", digest="b" * 64),
        ),
    )
    source = report(
        ("Account:income", "250.00"), ("Account:expense", "-75.00"), total="175.00"
    )
    first = project_financial_reports(history, (source,))
    second = project_financial_reports(history, (source, source))
    assert first == second
    assert first.reports[0].disposition is FinancialReportDisposition.SOURCE_BACKED
    assert first.reports[0].relationship_total == Decimal("175.00")
    assert first.reports[0].accepted_as_native is False
    assert first.read_only is True


def test_report_preserves_missing_relationship_and_total_mismatch_exceptions() -> None:
    history = project_financial_history(
        "quickbooks_online", (record("Account", "income"),)
    )
    missing = project_financial_reports(
        history, (report(("Account:missing", "10.00"), total="10.00"),)
    ).reports[0]
    assert missing.disposition is FinancialReportDisposition.HELD_MISSING_RELATIONSHIP
    assert missing.account_totals == (("Account:missing", Decimal("10.00")),)

    mismatch = project_financial_reports(
        history, (report(("Account:income", "10.00"), total="11.00"),)
    ).reports[0]
    assert mismatch.disposition is FinancialReportDisposition.HELD_TOTAL_MISMATCH
    assert mismatch.reported_total == Decimal("11.00")
    assert mismatch.relationship_total == Decimal("10.00")


def test_report_never_hides_held_account_source_exception() -> None:
    history = project_financial_history(
        "quickbooks_online",
        (
            record("Account", "income", digest="a" * 64),
            record("Account", "income", digest="b" * 64),
        ),
    )
    result = project_financial_reports(
        history, (report(("Account:income", "10.00"), total="10.00"),)
    )
    assert (
        result.reports[0].disposition
        is FinancialReportDisposition.HELD_SOURCE_EXCEPTION
    )
