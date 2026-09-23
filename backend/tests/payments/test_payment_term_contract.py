from dataclasses import fields
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.payments.contracts import (
    CardTransactionEvidence,
    StoredPaymentMethodReference,
)
from app.payments.money_authority import MoneyAuthorityService


def test_stored_payment_method_contract_excludes_raw_card_secrets():
    field_names = {field.name for field in fields(StoredPaymentMethodReference)}

    assert {"payment_method_token", "brand", "last4"}.issubset(field_names)
    assert field_names.isdisjoint(
        {"pan", "raw_pan", "card_number", "cvv", "cvc", "security_code"}
    )


def test_card_transaction_contract_preserves_settlement_and_deposit_separation():
    field_names = {field.name for field in fields(CardTransactionEvidence)}

    assert {"charged_at", "settlement_reference", "deposit_reference"}.issubset(
        field_names
    )
    assert "provider_transaction_id" in field_names


def test_customer_term_overrides_company_default_and_latest_version_wins():
    customer_id = uuid4()
    company_default = SimpleNamespace(
        customer_id=None, effective_from=date(2026, 1, 1), version=3
    )
    old_customer_term = SimpleNamespace(
        customer_id=customer_id, effective_from=date(2026, 1, 1), version=1
    )
    current_customer_term = SimpleNamespace(
        customer_id=customer_id, effective_from=date(2026, 1, 1), version=2
    )

    resolved = MoneyAuthorityService._resolve_term(
        (company_default, current_customer_term, old_customer_term), customer_id
    )

    assert resolved is current_customer_term
