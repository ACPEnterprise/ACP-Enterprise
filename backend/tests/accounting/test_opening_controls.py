from datetime import datetime, timezone
from decimal import Decimal

from app.accounting.opening_controls import (
    Disposition,
    OpeningControlPreviewRequest,
    SubledgerItem,
    TrialBalanceLine,
    preview_opening_controls,
)

CUTOFF = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)
DIGEST = "a" * 64


def line(
    identity: str,
    account_type: str,
    debit: str = "0",
    credit: str = "0",
    *,
    equity=None,
):  # type: ignore[no-untyped-def]
    return TrialBalanceLine(
        source_identity=identity,
        account_type=account_type,
        equity_category=equity,
        debit=Decimal(debit),
        credit=Decimal(credit),
        source_version="fixture-v1",
        source_digest=DIGEST,
    )


def item(identity: str, amount: str, *, native=None, as_of=CUTOFF, duplicate=False):  # type: ignore[no-untyped-def]
    return SubledgerItem(
        source_identity=identity,
        native_identity=native,
        party_identity=f"party-{identity}",
        document_identity=f"doc-{identity}",
        open_amount=Decimal(amount),
        as_of=as_of,
        source_digest=DIGEST,
        duplicate=duplicate,
    )


def request(**changes):  # type: ignore[no-untyped-def]
    values = {
        "realm_id": "fixture-realm",
        "package_identity": "opening-2026-09",
        "source_version": "qbo-v1",
        "cutoff_at": CUTOFF,
        "cutoff_timezone": "America/New_York",
        "acquired_at": CUTOFF,
        "source_as_of": CUTOFF,
        "source_manifest_digest": DIGEST,
        "trial_balance": (
            line("cash", "Bank", debit="100"),
            line("retained", "Equity", credit="100", equity="retained_earnings"),
        ),
        "ar_control_balance": Decimal(25),
        "ap_control_balance": Decimal(10),
        "source_ar": (item("invoice-1", "25"),),
        "native_ar": (item("invoice-1", "25", native="native-invoice-1"),),
        "source_ap": (item("bill-1", "10"),),
        "native_ap": (item("bill-1", "10", native="native-bill-1"),),
    }
    values.update(changes)
    return OpeningControlPreviewRequest(**values)


def test_balanced_opening_state_and_subledgers_are_approval_ready() -> None:
    result = preview_opening_controls(request())
    assert result.balanced
    assert result.ar_difference == 0
    assert result.ap_difference == 0
    assert result.status == "READY_FOR_APPROVAL"
    assert result.exceptions == ()


def test_unbalanced_trial_balance_never_creates_equity_plug() -> None:
    result = preview_opening_controls(
        request(
            trial_balance=(
                line("cash", "Bank", debit="101"),
                line("retained", "Equity", credit="100", equity="retained_earnings"),
            )
        )
    )
    assert not result.balanced
    assert result.status == "REVIEW_REQUIRED"
    assert any(row.control_family == "OPENING_EQUITY" for row in result.exceptions)


def test_opening_balance_equity_requires_explicit_review_reference() -> None:
    lines = (
        line("cash", "Bank", debit="100"),
        line("opening", "Equity", credit="100", equity="opening_equity"),
    )
    blocked = preview_opening_controls(request(trial_balance=lines))
    assert blocked.unexplained_equity
    assert blocked.status == "REVIEW_REQUIRED"
    admitted = preview_opening_controls(
        request(
            trial_balance=lines, opening_equity_review_reference="accountant-review-1"
        )
    )
    assert not admitted.unexplained_equity
    assert admitted.status == "READY_FOR_APPROVAL"


def test_ar_and_ap_control_differences_enter_review_queue() -> None:
    result = preview_opening_controls(
        request(ar_control_balance=Decimal(24), ap_control_balance=Decimal(11))
    )
    assert result.ar_difference == Decimal(-1)
    assert result.ap_difference == Decimal(1)
    assert {row.control_family for row in result.exceptions} == {"AR", "AP"}


def test_subledger_classifies_source_native_cutoff_and_duplicate_dispositions() -> None:
    stale = datetime(2026, 9, 29, 23, 59, tzinfo=timezone.utc)
    result = preview_opening_controls(
        request(
            ar_control_balance=Decimal(12),
            source_ar=(
                item("source-only", "3"),
                item("different", "4"),
                item("stale", "5", as_of=stale),
                item("duplicate", "0", duplicate=True),
            ),
            native_ar=(
                item("different", "9", native="native-different"),
                item("native-only", "2", native="native-only"),
                item("stale", "5", native="native-stale"),
            ),
        )
    )
    dispositions = {row.disposition for row in result.exceptions}
    assert {
        Disposition.SOURCE_ONLY,
        Disposition.AMOUNT_DIFFERENCE,
        Disposition.DATE_CUTOFF_DIFFERENCE,
        Disposition.DUPLICATE,
        Disposition.ACP_ONLY,
    } <= dispositions


def test_preview_digest_is_reproducible_and_preview_has_no_mutation_surface() -> None:
    first = preview_opening_controls(request())
    second = preview_opening_controls(request())
    assert first.evidence_digest == second.evidence_digest
    assert len(first.evidence_digest) == 64
