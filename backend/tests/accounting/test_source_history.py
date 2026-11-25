from datetime import date
from decimal import Decimal

from app.accounting.source_history import (
    FinancialHistoryDisposition,
    FinancialSourceRecord,
    project_financial_history,
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
