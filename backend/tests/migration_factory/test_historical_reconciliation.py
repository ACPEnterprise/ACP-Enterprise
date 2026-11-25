from datetime import datetime, timezone

from app.migration_factory.historical_read import HistoricalDomain
from app.migration_factory.historical_reconciliation import (
    ReconciliationDisposition,
    SourceHistoryRecord,
    reconcile_history,
)


def record(
    domain: HistoricalDomain, source_id: str, *parents: str, digest: str = "a" * 64
):
    return SourceHistoryRecord(
        domain,
        source_id,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        parents,
        {"label": source_id},
        digest,
    )


def test_reconciles_customer_location_job_appointment_and_communication_graph() -> None:
    rows = (
        record(HistoricalDomain.CUSTOMER, "c1"),
        record(HistoricalDomain.LOCATION, "l1", "customer:c1"),
        record(HistoricalDomain.JOB, "j1", "customer:c1", "location:l1"),
        record(HistoricalDomain.APPOINTMENT, "a1", "job:j1"),
        record(HistoricalDomain.ESTIMATE, "e1", "job:j1"),
        record(HistoricalDomain.INVOICE, "i1", "job:j1"),
        record(HistoricalDomain.PAYMENT, "p1", "invoice:i1"),
        record(HistoricalDomain.COMMUNICATION, "m1", "customer:c1", "job:j1"),
    )
    result = reconcile_history("housecall_pro", reversed(rows))
    assert all(
        row.disposition is ReconciliationDisposition.PROJECTED for row in result.records
    )
    assert result == reconcile_history("housecall_pro", rows)


def test_exact_duplicate_is_idempotent_but_changed_evidence_is_held() -> None:
    customer = record(HistoricalDomain.CUSTOMER, "c1")
    exact = reconcile_history("housecall_pro", (customer, customer))
    assert len(exact.records) == 1
    conflict = reconcile_history(
        "housecall_pro",
        (customer, record(HistoricalDomain.CUSTOMER, "c1", digest="b" * 64)),
    )
    assert conflict.records[0].disposition is ReconciliationDisposition.HELD_CONFLICT
    assert conflict.records[0].payload is None


def test_missing_parent_is_preserved_as_exception_without_payload_projection() -> None:
    result = reconcile_history(
        "housecall_pro", (record(HistoricalDomain.APPOINTMENT, "a1", "job:missing"),)
    )
    item = result.records[0]
    assert item.disposition is ReconciliationDisposition.HELD_MISSING_PARENT
    assert item.parent_source_keys == ("job:missing",)
    assert item.payload is None


def test_parent_namespace_must_match_exactly() -> None:
    result = reconcile_history(
        "housecall_pro",
        (
            record(HistoricalDomain.CUSTOMER, "shared"),
            record(HistoricalDomain.JOB, "j1", "location:shared"),
        ),
    )
    job = next(item for item in result.records if item.source_key == "job:j1")
    assert job.disposition is ReconciliationDisposition.HELD_MISSING_PARENT


def test_job_requires_verified_customer_and_location_relationships() -> None:
    result = reconcile_history(
        "housecall_pro",
        (
            record(HistoricalDomain.CUSTOMER, "c1"),
            record(HistoricalDomain.LOCATION, "l1", "customer:c1"),
            record(HistoricalDomain.JOB, "j1", "customer:c1"),
        ),
    )
    job = next(item for item in result.records if item.source_key == "job:j1")
    assert job.disposition is ReconciliationDisposition.HELD_INVALID_RELATIONSHIP
    assert job.payload is None


def test_wrong_parent_domain_is_held_even_when_source_identity_exists() -> None:
    result = reconcile_history(
        "housecall_pro",
        (
            record(HistoricalDomain.CUSTOMER, "c1"),
            record(HistoricalDomain.LOCATION, "l1", "customer:c1"),
            record(
                HistoricalDomain.JOB,
                "j1",
                "customer:c1",
                "location:l1",
                "invoice:i1",
            ),
            record(HistoricalDomain.INVOICE, "i1", "job:j1"),
        ),
    )
    job = next(item for item in result.records if item.source_key == "job:j1")
    invoice = next(item for item in result.records if item.source_key == "invoice:i1")
    assert job.disposition is ReconciliationDisposition.HELD_INVALID_RELATIONSHIP
    assert invoice.disposition is ReconciliationDisposition.HELD_PARENT_EXCEPTION


def test_parent_exception_propagates_without_projecting_descendants() -> None:
    result = reconcile_history(
        "housecall_pro",
        (
            record(HistoricalDomain.CUSTOMER, "c1", digest="a" * 64),
            record(HistoricalDomain.CUSTOMER, "c1", digest="b" * 64),
            record(HistoricalDomain.LOCATION, "l1", "customer:c1"),
            record(HistoricalDomain.JOB, "j1", "customer:c1", "location:l1"),
            record(HistoricalDomain.APPOINTMENT, "a1", "job:j1"),
        ),
    )
    by_key = {item.source_key: item for item in result.records}
    assert by_key["customer:c1"].disposition is ReconciliationDisposition.HELD_CONFLICT
    assert (
        by_key["location:l1"].disposition
        is ReconciliationDisposition.HELD_PARENT_EXCEPTION
    )
    assert (
        by_key["job:j1"].disposition is ReconciliationDisposition.HELD_PARENT_EXCEPTION
    )
    assert (
        by_key["appointment:a1"].disposition
        is ReconciliationDisposition.HELD_PARENT_EXCEPTION
    )
    assert all(item.payload is None for item in by_key.values())
