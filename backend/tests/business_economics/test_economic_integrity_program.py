import pytest
from app.business_economics.integrity import (
    EconomicMeaning,
    classify_source_semantics,
)


def test_revenue_and_settlement_are_mechanically_distinct() -> None:
    revenue = classify_source_semantics("accepted_earned_revenue")
    payment = classify_source_semantics("payment")
    invoice = classify_source_semantics("invoice")
    assert revenue.meaning is EconomicMeaning.REVENUE_EVIDENCE
    assert payment.meaning is EconomicMeaning.SETTLEMENT_EVIDENCE
    assert invoice.meaning is EconomicMeaning.POLICY_REQUIRED
    assert len({revenue.meaning, payment.meaning, invoice.meaning}) == 3


@pytest.mark.parametrize(
    "source",
    [
        "estimate",
        "inventory_transfer",
        "purchase_order_or_receipt",
    ],
)
def test_operational_evidence_does_not_become_income_or_expense(source: str) -> None:
    assert classify_source_semantics(source).meaning is EconomicMeaning.OPERATIONAL_ONLY


def test_service_agreement_and_callback_require_source_authority() -> None:
    assert (
        classify_source_semantics("service_agreement_billing_readiness").meaning
        is EconomicMeaning.SOURCE_REQUIRED
    )
    callback = classify_source_semantics("callback_label")
    assert callback.meaning is EconomicMeaning.SOURCE_REQUIRED
    assert "causality" in callback.limitation


def test_unknown_source_fails_closed() -> None:
    with pytest.raises(ValueError, match="no accepted Economics semantic"):
        classify_source_semantics("pretend_revenue")
