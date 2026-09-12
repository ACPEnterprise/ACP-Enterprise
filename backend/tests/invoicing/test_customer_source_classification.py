from datetime import date, datetime, timezone

from app.invoicing.source_classification import (
    CustomerEvidenceClassification,
    historical_source_evidence,
    native_evidence,
    unavailable_source_evidence,
)

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)
AS_OF = date(2026, 9, 12)


def test_native_evidence_classifies_current_partial_and_conflicting() -> None:
    values = {"currency": "USD", "open_balance": "125.00"}
    common = {
        "company_id": "company-1",
        "customer_id": "customer-1",
        "as_of": AS_OF,
        "acquired_at": NOW,
        "values": values,
    }
    current = native_evidence(**common, partial=False, conflicting=False)
    partial = native_evidence(**common, partial=True, conflicting=False)
    conflicting = native_evidence(**common, partial=False, conflicting=True)
    assert (
        current.classification is CustomerEvidenceClassification.CURRENT_AUTHORITATIVE
    )
    assert partial.classification is CustomerEvidenceClassification.PARTIAL
    assert conflicting.classification is CustomerEvidenceClassification.CONFLICTING
    assert current.company_id == "company-1"
    assert current.customer_id == "customer-1"
    assert (
        current.evidence_digest
        == native_evidence(**common, partial=False, conflicting=False).evidence_digest
    )
    assert current.evidence_digest != native_evidence(
        **{**common, "company_id": "company-2"}, partial=False, conflicting=False
    ).evidence_digest


def test_source_evidence_preserves_historical_stale_partial_and_conflicting_truth() -> (
    None
):
    common = {
        "company_id": "company-1",
        "customer_id": "customer-1",
        "source_system": "housecall_pro",
        "source_record_identity": "hcp-customer-1",
        "acquired_at": NOW,
        "evidence_digest": "d" * 64,
    }
    historical = historical_source_evidence(**common, complete=True)
    stale = historical_source_evidence(**common, complete=True, stale=True)
    partial = historical_source_evidence(**common, complete=False)
    conflicting = historical_source_evidence(**common, complete=True, conflicting=True)
    assert (
        historical.classification
        is CustomerEvidenceClassification.HISTORICAL_SOURCE_EVIDENCE
    )
    assert stale.classification is CustomerEvidenceClassification.STALE
    assert partial.classification is CustomerEvidenceClassification.PARTIAL
    assert conflicting.classification is CustomerEvidenceClassification.CONFLICTING
    assert all(
        item.authority == "historical_source_evidence_only"
        for item in (historical, stale, partial, conflicting)
    )


def test_unavailable_source_does_not_fabricate_identity_digest_or_dates() -> None:
    item = unavailable_source_evidence(
        company_id="company-1",
        customer_id="customer-1",
        source_system="quickbooks_online",
    )
    assert item.classification is CustomerEvidenceClassification.UNAVAILABLE
    assert item.source_record_identity is None
    assert item.evidence_digest is None
    assert item.as_of is None
    assert item.acquired_at is None
