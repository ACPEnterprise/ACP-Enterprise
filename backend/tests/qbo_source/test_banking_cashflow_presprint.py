from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.qbo_source.presprint_reconciliation import (
    BankAccountIdentity,
    BankMatchCandidate,
    BankMatchState,
    BankTransactionEvidence,
    BankTransactionKind,
    BankTransactionState,
    CashFlowMovement,
    CashFlowState,
    build_cash_flow_report,
    close_bank_statement,
    deterministic_bank_match,
    reconcile_bank_statement,
    validate_bank_replay,
)

ACCOUNT = BankAccountIdentity(
    "company-1", "bank-1", "Example Bank", "Operating", "USD", "fixture"
)
AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)


def tx(
    provider_id: str,
    amount: str,
    *,
    related: str | None = None,
    group_key: str | None = None,
    state: BankTransactionState = BankTransactionState.POSTED,
    cleared: bool = False,
) -> BankTransactionEvidence:
    return BankTransactionEvidence(
        ACCOUNT,
        provider_id,
        "v1",
        f"digest-{provider_id}",
        AS_OF,
        date(2026, 9, 30),
        Decimal(amount),
        BankTransactionKind.DEPOSIT,
        state,
        related,
        group_key,
        related,
        cleared,
    )


def test_match_requires_explicit_identity_and_exact_values() -> None:
    decision = deterministic_bank_match(
        tx("bank-1", "100.00", related="invoice-1"),
        [
            BankMatchCandidate(
                "invoice-1", "INVOICE_PAYMENT", Decimal("100.00"), date(2026, 9, 30)
            )
        ],
    )
    assert decision.state is BankMatchState.MATCHED

    unmatched = deterministic_bank_match(
        tx("bank-2", "100.00"),
        [
            BankMatchCandidate(
                "invoice-2", "INVOICE_PAYMENT", Decimal("100.00"), date(2026, 9, 30)
            )
        ],
    )
    assert unmatched.state is BankMatchState.UNMATCHED


def test_pending_or_ambiguous_match_requires_review() -> None:
    pending = deterministic_bank_match(
        tx("bank-3", "100.00", related="invoice-3", state=BankTransactionState.PENDING),
        [
            BankMatchCandidate(
                "invoice-3", "INVOICE_PAYMENT", Decimal("100.00"), date(2026, 9, 30)
            )
        ],
    )
    assert pending.state is BankMatchState.REVIEW_REQUIRED
    ambiguous = deterministic_bank_match(
        tx("bank-4", "100.00", related="invoice-4"),
        [
            BankMatchCandidate(
                "invoice-4", "INVOICE_PAYMENT", Decimal("100.00"), date(2026, 9, 30)
            ),
            BankMatchCandidate(
                "invoice-4", "INVOICE_PAYMENT", Decimal("100.00"), date(2026, 9, 30)
            ),
        ],
    )
    assert ambiguous.state is BankMatchState.REVIEW_REQUIRED


def test_bank_replay_is_idempotent_but_digest_drift_fails() -> None:
    original = tx("bank-replay", "25.00")
    assert validate_bank_replay([original, original]).state.value == "PASS"
    drifted = BankTransactionEvidence(
        ACCOUNT,
        "bank-replay",
        "v2",
        "different",
        AS_OF,
        date(2026, 9, 30),
        Decimal("25.00"),
        BankTransactionKind.DEPOSIT,
        BankTransactionState.POSTED,
    )
    assert validate_bank_replay([original, drifted]).state.value == "FAIL"


def test_reconciliation_requires_zero_difference_and_closes_immutably() -> None:
    result = reconcile_bank_statement(
        ACCOUNT,
        "statement-1",
        date(2026, 9, 30),
        Decimal("100.00"),
        Decimal("250.00"),
        [tx("bank-5", "150.00", cleared=True)],
    )
    assert result.status == "READY_TO_CLOSE"
    snapshot = close_bank_statement(
        result,
        preparer="accountant-1",
        reviewer="owner-1",
        closed_at=AS_OF,
        source_digest="statement-digest",
    )
    assert snapshot.cleared_transaction_ids == ("bank-5",)
    assert snapshot.ending_balance == Decimal("250.00")

    not_ready = reconcile_bank_statement(
        ACCOUNT,
        "statement-2",
        date(2026, 9, 30),
        Decimal("100.00"),
        Decimal("251.00"),
        [tx("bank-6", "150.00", cleared=True)],
    )
    with pytest.raises(ValueError, match="difference"):
        close_bank_statement(
            not_ready,
            preparer="accountant-1",
            reviewer=None,
            closed_at=AS_OF,
            source_digest="x",
        )


def movement(
    movement_id: str, category: str, amount: str, review: bool = False
) -> CashFlowMovement:
    return CashFlowMovement(
        movement_id,
        category,
        Decimal(amount),
        date(2026, 9, 30),
        f"src-{movement_id}",
        "digest",
        review,
    )


def test_cash_flow_ties_and_preserves_classification_review() -> None:
    report = build_cash_flow_report(
        cutoff=date(2026, 9, 30),
        beginning_cash=Decimal(1000),
        ending_cash=Decimal(850),
        movements=[
            movement("1", "OPERATING", "-200"),
            movement("2", "FINANCING", "50"),
        ],
    )
    assert report.state is CashFlowState.READY
    assert report.net_change == Decimal(-150)

    review = build_cash_flow_report(
        cutoff=date(2026, 9, 30),
        beginning_cash=Decimal(1000),
        ending_cash=Decimal(850),
        movements=[movement("3", "OPERATING", "-150", review=True)],
    )
    assert review.state is CashFlowState.REVIEW_REQUIRED


def test_cash_flow_does_not_silently_accept_untied_cash() -> None:
    report = build_cash_flow_report(
        cutoff=date(2026, 9, 30),
        beginning_cash=Decimal(1000),
        ending_cash=Decimal(900),
        movements=[movement("4", "OPERATING", "-50")],
    )
    assert report.state is CashFlowState.REVIEW_REQUIRED


def test_cash_flow_rejects_unclassified_movement() -> None:
    report = build_cash_flow_report(
        cutoff=date(2026, 9, 30),
        beginning_cash=Decimal(1000),
        ending_cash=Decimal(900),
        movements=[movement("5", "TRANSFER", "-100")],
    )
    assert report.state is CashFlowState.REVIEW_REQUIRED
