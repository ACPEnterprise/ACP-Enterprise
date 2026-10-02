from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.accounting.banking import (
    CanonicalMatchCandidate,
    MatchState,
    NormalizedBankEvidence,
    control_integrity,
    deterministic_match,
    grouped_deposit_candidate,
    normalize_evidence,
    reconciliation_preview,
    source_transition,
    transfer_control,
)
from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.models import BankAccount, BankReconciliation, BankTransaction
from app.main import app

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
DIGEST = "a" * 64


def evidence(**changes: object) -> NormalizedBankEvidence:
    values: dict[str, object] = {
        "external_transaction_id": "bank-tx-1",
        "source_version": "v1",
        "source_digest": DIGEST,
        "acquired_at": NOW,
        "source_as_of": NOW,
        "posted_date": date(2026, 10, 1),
        "effective_date": date(2026, 10, 1),
        "amount": Decimal("125.00"),
        "currency": "USD",
        "direction": "inflow",
        "kind": "deposit",
        "description": "Sanitized fixture deposit",
        "state": "posted",
    }
    values.update(changes)
    return NormalizedBankEvidence(**values)  # type: ignore[arg-type]


def test_normalized_bank_evidence_requires_safe_identity_amount_and_digest() -> None:
    assert normalize_evidence(evidence()).external_transaction_id == "bank-tx-1"
    with pytest.raises(AccountingValidation, match="digest"):
        normalize_evidence(evidence(source_digest="short"))
    with pytest.raises(AccountingValidation, match="positive"):
        normalize_evidence(evidence(amount=Decimal(0)))


def test_duplicate_replay_and_pending_to_posted_are_deterministic() -> None:
    assert (
        source_transition(
            existing_state="posted",
            existing_digest=DIGEST,
            incoming_state="posted",
            incoming_digest=DIGEST,
        )
        == "idempotent_replay"
    )
    assert (
        source_transition(
            existing_state="pending",
            existing_digest="b" * 64,
            incoming_state="posted",
            incoming_digest=DIGEST,
        )
        == "promote_to_posted"
    )
    with pytest.raises(AccountingConflict, match="drifted"):
        source_transition(
            existing_state="posted",
            existing_digest="b" * 64,
            incoming_state="posted",
            incoming_digest=DIGEST,
        )


def test_auto_match_requires_one_exact_explicit_source_link() -> None:
    candidate = CanonicalMatchCandidate(
        "customer_payment",
        "payment-1",
        Decimal("125.00"),
        "USD",
        date(2026, 10, 1),
        "bank-tx-1",
    )
    decision = deterministic_match(evidence(related_identity="payment-1"), (candidate,))
    assert decision.state is MatchState.MATCHED
    assert decision.deterministic is True

    same_external_id_without_lineage = deterministic_match(evidence(), (candidate,))
    assert same_external_id_without_lineage.state is MatchState.REVIEW_REQUIRED

    ambiguous = deterministic_match(
        evidence(related_identity="payment-1"), (candidate, candidate)
    )
    assert ambiguous.state is MatchState.AMBIGUOUS
    assert ambiguous.deterministic is False

    review = deterministic_match(
        evidence(),
        (
            CanonicalMatchCandidate(
                "vendor_payment",
                "ap-1",
                Decimal("125.00"),
                "USD",
                date(2026, 10, 1),
                None,
            ),
        ),
    )
    assert review.state is MatchState.REVIEW_REQUIRED


def test_grouped_deposit_clears_unique_components_without_new_revenue() -> None:
    candidate = grouped_deposit_candidate(
        target_identity="deposit-1",
        external_transaction_id="bank-tx-1",
        currency="USD",
        effective_date=date(2026, 10, 1),
        components=(("receipt-1", Decimal("75.00")), ("receipt-2", Decimal("50.00"))),
    )
    assert candidate.amount == Decimal("125.00")
    assert (
        deterministic_match(evidence(related_identity="deposit-1"), (candidate,)).state
        is MatchState.MATCHED
    )
    control = control_integrity(
        bank_delta=Decimal("125.00"),
        cash_gl_delta=Decimal(0),
        undeposited_clearing=Decimal("125.00"),
    )
    assert control["state"] == "matched"
    assert "never create revenue" in str(control["double_recognition_guard"])
    with pytest.raises(AccountingValidation, match="unique"):
        grouped_deposit_candidate(
            target_identity="deposit-2",
            external_transaction_id="bank-tx-2",
            currency="USD",
            effective_date=date(2026, 10, 1),
            components=(("receipt-1", Decimal(50)), ("receipt-1", Decimal(75))),
        )


@pytest.mark.parametrize(
    "kind", ["fee", "merchant_settlement", "payroll", "vendor_payment"]
)
def test_supported_control_transaction_categories(kind: str) -> None:
    assert normalize_evidence(evidence(kind=kind)).kind == kind


def test_company_bank_transfer_is_balance_sheet_neutral() -> None:
    result = transfer_control(
        source_account_id=UUID(int=1),
        destination_account_id=UUID(int=2),
        source_amount=Decimal(400),
        destination_amount=Decimal(400),
    )
    assert result["state"] == "matched"
    assert result["income_expense_effect"] == Decimal(0)


def test_reconciliation_closes_only_at_zero_with_explained_cutoff_items() -> None:
    ready = reconciliation_preview(
        ending_balance=Decimal(1000),
        book_balance=Decimal(900),
        cleared_total=Decimal(125),
        outstanding_total=Decimal(25),
        unresolved_count=0,
    )
    assert ready.status == "ready_to_close"
    assert ready.difference == Decimal(0)
    assert (
        reconciliation_preview(
            ending_balance=Decimal(1001),
            book_balance=Decimal(900),
            cleared_total=Decimal(125),
            outstanding_total=Decimal(25),
            unresolved_count=0,
        ).status
        == "review_required"
    )
    assert (
        reconciliation_preview(
            ending_balance=Decimal(1000),
            book_balance=Decimal(900),
            cleared_total=Decimal(125),
            outstanding_total=Decimal(25),
            unresolved_count=1,
        ).status
        == "review_required"
    )


def test_bank_models_encode_company_scope_and_immutable_close_controls() -> None:
    assert {column.name for column in BankAccount.__table__.columns} >= {
        "company_id",
        "masked_identity",
        "source_digest",
        "source_as_of",
        "opening_balance_provenance",
    }
    assert {column.name for column in BankTransaction.__table__.columns} >= {
        "external_transaction_id",
        "related_identity",
        "group_key",
        "prior_source_digest",
        "acquired_at",
        "state",
    }
    assert {column.name for column in BankReconciliation.__table__.columns} >= {
        "cleared_transaction_ids",
        "outstanding_items",
        "reviewer_user_id",
        "closed_at",
        "evidence_digest",
    }


def test_banking_api_is_default_deny_and_has_no_reopen_or_money_movement() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/accounting/banking/accounts").status_code == 401
    paths = app.openapi()["paths"]
    assert "/api/v1/accounting/banking/accounts" in paths
    assert (
        "/api/v1/accounting/banking/accounts/{bank_account_id}/transactions/"
        "{transaction_id}/match"
    ) in paths
    banking_paths = [path for path in paths if "/accounting/banking" in path]
    assert not any("reopen" in path for path in banking_paths)
    assert not any("transfer" in path for path in banking_paths)
