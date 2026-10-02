"""Read-only QuickBooks replacement pre-sprint control validators.

These validators inspect proposed evidence in memory. They do not post journals,
change balances, reconcile bank accounts, or persist accounting mutations.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class CheckState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ReconciliationCheck:
    check: str
    state: CheckState
    explanation: str


@dataclass(frozen=True)
class LedgerLine:
    source_identity: str
    debit: Decimal
    credit: Decimal


def validate_double_entry(lines: Iterable[LedgerLine]) -> ReconciliationCheck:
    rows = tuple(lines)
    if not rows:
        return ReconciliationCheck(
            "double_entry", CheckState.UNAVAILABLE, "No ledger evidence was supplied."
        )
    if any(line.debit < 0 or line.credit < 0 for line in rows):
        return ReconciliationCheck(
            "double_entry", CheckState.FAIL, "Debit and credit amounts cannot be negative."
        )
    debits = sum((line.debit for line in rows), Decimal(0))
    credits = sum((line.credit for line in rows), Decimal(0))
    if debits != credits:
        return ReconciliationCheck(
            "double_entry",
            CheckState.FAIL,
            f"Debits {debits} do not equal credits {credits}.",
        )
    return ReconciliationCheck("double_entry", CheckState.PASS, "Debits equal credits.")


def validate_control_tie(
    name: str, subledger_total: Decimal | None, control_total: Decimal | None
) -> ReconciliationCheck:
    if subledger_total is None or control_total is None:
        return ReconciliationCheck(
            name, CheckState.UNAVAILABLE, "Both subledger and control evidence are required."
        )
    if subledger_total != control_total:
        return ReconciliationCheck(
            name,
            CheckState.FAIL,
            f"Subledger {subledger_total} does not equal control {control_total}.",
        )
    return ReconciliationCheck(name, CheckState.PASS, "Subledger equals control account.")


def validate_balance_sheet(
    assets: Decimal | None,
    liabilities: Decimal | None,
    equity: Decimal | None,
    current_earnings: Decimal | None,
) -> ReconciliationCheck:
    values = (assets, liabilities, equity, current_earnings)
    if any(value is None for value in values):
        return ReconciliationCheck(
            "balance_sheet", CheckState.UNAVAILABLE, "All balance-sheet control values are required."
        )
    assert assets is not None
    assert liabilities is not None
    assert equity is not None
    assert current_earnings is not None
    if assets != liabilities + equity + current_earnings:
        return ReconciliationCheck(
            "balance_sheet",
            CheckState.FAIL,
            "Assets do not equal liabilities, equity, and current earnings.",
        )
    return ReconciliationCheck("balance_sheet", CheckState.PASS, "Balance sheet balances.")


def validate_source_replay(
    records: Iterable[Mapping[str, str]],
) -> ReconciliationCheck:
    """Require repeated source identity to carry the same source digest."""

    seen: dict[str, str] = {}
    for record in records:
        identity = record.get("source_identity")
        digest = record.get("source_digest")
        if not identity or not digest:
            return ReconciliationCheck(
                "source_replay", CheckState.UNAVAILABLE, "Source identity and digest are required."
            )
        previous = seen.setdefault(identity, digest)
        if previous != digest:
            return ReconciliationCheck(
                "source_replay",
                CheckState.FAIL,
                f"Source identity {identity} replayed with a different digest.",
            )
    if not seen:
        return ReconciliationCheck(
            "source_replay", CheckState.UNAVAILABLE, "No source records were supplied."
        )
    return ReconciliationCheck("source_replay", CheckState.PASS, "Source replay is idempotent.")
