from decimal import Decimal

from app.payments.money_authority import (
    ExpectedCollectionEvidence,
    _summarize_amounts,
    compose_expected_collections,
)
from app.payments.router import router
from fastapi import FastAPI


def evidence(
    amount: str | None,
    state: str = "AVAILABLE",
    *,
    basis: str,
) -> ExpectedCollectionEvidence:
    return ExpectedCollectionEvidence(
        amount=None if amount is None else Decimal(amount),
        currency="USD",
        evidence_state=state,  # type: ignore[arg-type]
        evidence_basis=basis,
    )


def test_expected_collections_combines_only_authoritative_cod_and_due_ar() -> None:
    result = compose_expected_collections(
        cod=evidence("3000.00", basis="COMPLETED_COD_INVOICE"),
        due_today=evidence("2100.00", basis="OPEN_INVOICE_DUE_DATE"),
    )
    assert result.amount == Decimal("5100.00")
    assert result.currency == "USD"
    assert result.evidence_state == "AVAILABLE"


def test_net_terms_work_today_is_not_expected_cash_until_invoice_is_due() -> None:
    # Scheduled NET 15 work contributes no COD amount. A prior Invoice whose
    # contractual due date is today remains independently included.
    result = compose_expected_collections(
        cod=evidence("0.00", "MEASURED_ZERO", basis="NO_QUALIFYING_COD"),
        due_today=evidence("3000.00", basis="OPEN_INVOICE_DUE_DATE"),
    )
    assert result.amount == Decimal("3000.00")


def test_missing_cod_or_terms_evidence_never_becomes_zero() -> None:
    result = compose_expected_collections(
        cod=evidence(None, "UNAVAILABLE", basis="SCHEDULED_COD_UNAVAILABLE"),
        due_today=evidence("11000.00", basis="OPEN_INVOICE_DUE_DATE"),
    )
    assert result.amount is None
    assert result.evidence_state == "INCOMPLETE"


def test_conflicting_currency_cannot_be_aggregated() -> None:
    result = _summarize_amounts(((Decimal("10.00"), "USD"), (Decimal("20.00"), "CAD")))
    assert result.amount is None
    assert result.evidence_state == "CONFLICTING"


def test_money_api_requires_explicit_period_and_as_of_contract() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/api/v1/payments/money-position"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["period_start"]["required"] is True
    assert parameters["period_end"]["required"] is True
    assert parameters["as_of"]["required"] is True
    assert parameters["branch_id"]["required"] is False
