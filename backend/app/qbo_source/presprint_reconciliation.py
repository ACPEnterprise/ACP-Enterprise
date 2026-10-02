"""Read-only QuickBooks replacement pre-sprint control validators.

These validators inspect proposed evidence in memory. They do not post journals,
change balances, reconcile bank accounts, or persist accounting mutations.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
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


class BankTransactionState(StrEnum):
    PENDING = "PENDING"
    POSTED = "POSTED"


class BankTransactionKind(StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    CHECK = "CHECK"
    ACH = "ACH"
    TRANSFER = "TRANSFER"
    MERCHANT_DEPOSIT = "MERCHANT_DEPOSIT"
    MERCHANT_FEE = "MERCHANT_FEE"
    BANK_FEE = "BANK_FEE"
    INTEREST = "INTEREST"
    REFUND = "REFUND"
    REVERSAL = "REVERSAL"
    OWNER_MOVEMENT = "OWNER_MOVEMENT"
    OTHER = "OTHER"


class BankMatchState(StrEnum):
    MATCHED = "MATCHED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNMATCHED = "UNMATCHED"


class CashFlowState(StrEnum):
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class BankAccountIdentity:
    """Provider-neutral company-scoped bank account identity."""

    company_id: str
    account_id: str
    institution_name: str
    account_label: str
    currency: str
    source_system: str


@dataclass(frozen=True)
class BankTransactionEvidence:
    """A sanitized imported transaction; it is evidence, not a posting."""

    account: BankAccountIdentity
    provider_transaction_id: str
    source_version: str
    source_digest: str
    as_of: datetime
    transaction_date: date
    amount: Decimal
    kind: BankTransactionKind
    state: BankTransactionState
    reference: str | None = None
    group_key: str | None = None
    related_identity: str | None = None
    cleared: bool = False


@dataclass(frozen=True)
class BankMatchCandidate:
    target_identity: str
    target_kind: str
    amount: Decimal
    transaction_date: date
    explicit_group_key: str | None = None


@dataclass(frozen=True)
class BankMatchDecision:
    state: BankMatchState
    transaction_id: str
    target_identity: str | None
    reason: str


def deterministic_bank_match(
    transaction: BankTransactionEvidence,
    candidates: Sequence[BankMatchCandidate],
) -> BankMatchDecision:
    """Match only exact source-linked evidence; never fuzzy-auto-match."""

    if transaction.state is not BankTransactionState.POSTED:
        return BankMatchDecision(
            BankMatchState.REVIEW_REQUIRED,
            transaction.provider_transaction_id,
            None,
            "Pending transactions require review before matching.",
        )
    exact = [
        candidate
        for candidate in candidates
        if candidate.amount == transaction.amount
        and candidate.transaction_date == transaction.transaction_date
        and (
            transaction.related_identity == candidate.target_identity
            or (
                transaction.group_key is not None
                and transaction.group_key == candidate.explicit_group_key
            )
        )
    ]
    if len(exact) == 1:
        return BankMatchDecision(
            BankMatchState.MATCHED,
            transaction.provider_transaction_id,
            exact[0].target_identity,
            "Exact amount, date, and explicit source relationship matched.",
        )
    if len(exact) > 1:
        return BankMatchDecision(
            BankMatchState.REVIEW_REQUIRED,
            transaction.provider_transaction_id,
            None,
            "Multiple exact candidates remain ambiguous.",
        )
    return BankMatchDecision(
        BankMatchState.UNMATCHED,
        transaction.provider_transaction_id,
        None,
        "No deterministic source-linked candidate was found.",
    )


def validate_bank_replay(
    transactions: Iterable[BankTransactionEvidence],
) -> ReconciliationCheck:
    """Reject provider identity drift while allowing idempotent replay."""

    return validate_source_replay(
        {
            "source_identity": row.provider_transaction_id,
            "source_digest": row.source_digest,
        }
        for row in transactions
    )


@dataclass(frozen=True)
class BankReconciliationResult:
    account_id: str
    statement_id: str
    statement_end: date
    opening_balance: Decimal
    ending_balance: Decimal
    cleared_total: Decimal
    difference: Decimal
    status: str
    cleared_transaction_ids: tuple[str, ...]
    unresolved_transaction_ids: tuple[str, ...]


@dataclass(frozen=True)
class BankReconciliationSnapshot:
    """Immutable close evidence; reopening must create a new review event."""

    statement_id: str
    account_id: str
    statement_end: date
    ending_balance: Decimal
    cleared_transaction_ids: tuple[str, ...]
    unresolved_transaction_ids: tuple[str, ...]
    preparer: str
    reviewer: str | None
    closed_at: datetime
    source_digest: str


def reconcile_bank_statement(
    account: BankAccountIdentity,
    statement_id: str,
    statement_end: date,
    opening_balance: Decimal,
    ending_balance: Decimal,
    transactions: Iterable[BankTransactionEvidence],
    unresolved_transaction_ids: Iterable[str] = (),
) -> BankReconciliationResult:
    rows = tuple(transactions)
    if any(row.account != account for row in rows):
        raise ValueError(
            "All statement transactions must belong to the selected account."
        )
    cleared = tuple(
        row
        for row in rows
        if row.cleared
        and row.state is BankTransactionState.POSTED
        and row.transaction_date <= statement_end
    )
    unresolved = tuple(sorted(set(unresolved_transaction_ids)))
    cleared_total = sum((row.amount for row in cleared), Decimal(0))
    difference = ending_balance - (opening_balance + cleared_total)
    status = (
        "READY_TO_CLOSE" if difference == 0 and not unresolved else "REVIEW_REQUIRED"
    )
    return BankReconciliationResult(
        account.account_id,
        statement_id,
        statement_end,
        opening_balance,
        ending_balance,
        cleared_total,
        difference,
        status,
        tuple(row.provider_transaction_id for row in cleared),
        unresolved,
    )


def close_bank_statement(
    result: BankReconciliationResult,
    *,
    preparer: str,
    reviewer: str | None,
    closed_at: datetime,
    source_digest: str,
) -> BankReconciliationSnapshot:
    if result.status != "READY_TO_CLOSE":
        raise ValueError(
            "A statement with a difference or unresolved items cannot be closed."
        )
    return BankReconciliationSnapshot(
        result.statement_id,
        result.account_id,
        result.statement_end,
        result.ending_balance,
        result.cleared_transaction_ids,
        result.unresolved_transaction_ids,
        preparer,
        reviewer,
        closed_at,
        source_digest,
    )


@dataclass(frozen=True)
class CashFlowMovement:
    movement_id: str
    category: str
    amount: Decimal
    as_of: date
    source_identity: str
    source_digest: str
    classification_review_required: bool = False


@dataclass(frozen=True)
class CashFlowReport:
    state: CashFlowState
    cutoff: date
    beginning_cash: Decimal | None
    operating: Decimal | None
    investing: Decimal | None
    financing: Decimal | None
    net_change: Decimal | None
    ending_cash: Decimal | None
    explanation: str


def build_cash_flow_report(
    *,
    cutoff: date,
    beginning_cash: Decimal | None,
    ending_cash: Decimal | None,
    movements: Iterable[CashFlowMovement],
) -> CashFlowReport:
    rows = tuple(movements)
    if beginning_cash is None or ending_cash is None or not rows:
        return CashFlowReport(
            CashFlowState.UNAVAILABLE,
            cutoff,
            beginning_cash,
            None,
            None,
            None,
            None,
            ending_cash,
            "Beginning, ending, and classified cash evidence are required.",
        )
    if any(row.as_of > cutoff for row in rows):
        return CashFlowReport(
            CashFlowState.REVIEW_REQUIRED,
            cutoff,
            beginning_cash,
            None,
            None,
            None,
            None,
            ending_cash,
            "A movement is after the report cutoff.",
        )
    if any(row.classification_review_required for row in rows):
        return CashFlowReport(
            CashFlowState.REVIEW_REQUIRED,
            cutoff,
            beginning_cash,
            None,
            None,
            None,
            None,
            ending_cash,
            "At least one cash movement requires classification review.",
        )
    if any(row.category not in {"OPERATING", "INVESTING", "FINANCING"} for row in rows):
        return CashFlowReport(
            CashFlowState.REVIEW_REQUIRED,
            cutoff,
            beginning_cash,
            None,
            None,
            None,
            None,
            ending_cash,
            "A cash movement has no approved operating, investing, or financing classification.",
        )
    totals = {
        "OPERATING": sum(
            (row.amount for row in rows if row.category == "OPERATING"), Decimal(0)
        ),
        "INVESTING": sum(
            (row.amount for row in rows if row.category == "INVESTING"), Decimal(0)
        ),
        "FINANCING": sum(
            (row.amount for row in rows if row.category == "FINANCING"), Decimal(0)
        ),
    }
    net_change = sum(totals.values(), Decimal(0))
    if beginning_cash + net_change != ending_cash:
        return CashFlowReport(
            CashFlowState.REVIEW_REQUIRED,
            cutoff,
            beginning_cash,
            totals["OPERATING"],
            totals["INVESTING"],
            totals["FINANCING"],
            net_change,
            ending_cash,
            "Beginning cash plus classified movement does not tie to ending cash.",
        )
    return CashFlowReport(
        CashFlowState.READY,
        cutoff,
        beginning_cash,
        totals["OPERATING"],
        totals["INVESTING"],
        totals["FINANCING"],
        net_change,
        ending_cash,
        "Cash flow ties beginning cash, classified movement, and ending cash.",
    )


def validate_double_entry(lines: Iterable[LedgerLine]) -> ReconciliationCheck:
    rows = tuple(lines)
    if not rows:
        return ReconciliationCheck(
            "double_entry", CheckState.UNAVAILABLE, "No ledger evidence was supplied."
        )
    if any(line.debit < 0 or line.credit < 0 for line in rows):
        return ReconciliationCheck(
            "double_entry",
            CheckState.FAIL,
            "Debit and credit amounts cannot be negative.",
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
            name,
            CheckState.UNAVAILABLE,
            "Both subledger and control evidence are required.",
        )
    if subledger_total != control_total:
        return ReconciliationCheck(
            name,
            CheckState.FAIL,
            f"Subledger {subledger_total} does not equal control {control_total}.",
        )
    return ReconciliationCheck(
        name, CheckState.PASS, "Subledger equals control account."
    )


def validate_balance_sheet(
    assets: Decimal | None,
    liabilities: Decimal | None,
    equity: Decimal | None,
    current_earnings: Decimal | None,
) -> ReconciliationCheck:
    values = (assets, liabilities, equity, current_earnings)
    if any(value is None for value in values):
        return ReconciliationCheck(
            "balance_sheet",
            CheckState.UNAVAILABLE,
            "All balance-sheet control values are required.",
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
    return ReconciliationCheck(
        "balance_sheet", CheckState.PASS, "Balance sheet balances."
    )


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
                "source_replay",
                CheckState.UNAVAILABLE,
                "Source identity and digest are required.",
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
    return ReconciliationCheck(
        "source_replay", CheckState.PASS, "Source replay is idempotent."
    )
