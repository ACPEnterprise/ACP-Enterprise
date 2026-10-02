from decimal import Decimal

from app.qbo_source.presprint_reconciliation import (
    CheckState,
    LedgerLine,
    validate_balance_sheet,
    validate_control_tie,
    validate_double_entry,
    validate_source_replay,
)


def test_double_entry_requires_evidence_and_balances() -> None:
    assert validate_double_entry(()).state is CheckState.UNAVAILABLE
    result = validate_double_entry(
        (
            LedgerLine("j1:d", Decimal(10), Decimal(0)),
            LedgerLine("j1:c", Decimal(0), Decimal(10)),
        )
    )
    assert result.state is CheckState.PASS


def test_double_entry_rejects_variance() -> None:
    result = validate_double_entry((LedgerLine("j1", Decimal(10), Decimal(9)),))
    assert result.state is CheckState.FAIL


def test_control_tie_and_balance_sheet_are_fail_closed() -> None:
    assert validate_control_tie("ar", None, Decimal(1)).state is CheckState.UNAVAILABLE
    assert validate_control_tie("ar", Decimal(10), Decimal(10)).state is CheckState.PASS
    assert validate_balance_sheet(Decimal(10), Decimal(4), Decimal(5), Decimal(1)).state is CheckState.PASS
    assert validate_balance_sheet(Decimal(10), Decimal(4), Decimal(5), Decimal(2)).state is CheckState.FAIL


def test_source_replay_rejects_digest_drift() -> None:
    same = ({"source_identity": "invoice-1", "source_digest": "a"},) * 2
    assert validate_source_replay(same).state is CheckState.PASS
    assert validate_source_replay(
        (
            {"source_identity": "invoice-1", "source_digest": "a"},
            {"source_identity": "invoice-1", "source_digest": "b"},
        )
    ).state is CheckState.FAIL
