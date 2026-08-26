from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ControlKind(str, Enum):
    TRIAL_BALANCE = "trial_balance"
    ACCOUNT_LIST = "account_list"
    AR_AGING_DETAIL = "ar_aging_detail"
    CUSTOMER_BALANCE_DETAIL = "customer_balance_detail"
    OPEN_INVOICES = "open_invoices"
    AP_AGING_DETAIL = "ap_aging_detail"
    VENDOR_BALANCE_DETAIL = "vendor_balance_detail"
    UNPAID_BILLS = "unpaid_bills"
    PROFIT_AND_LOSS = "profit_and_loss"
    BALANCE_SHEET = "balance_sheet"


class ReconciliationState(str, Enum):
    MATCHED = "matched"
    EXCEPTION = "exception"
    MISSING_SOURCE_EVIDENCE = "missing_source_evidence"
    MISSING_CONTROL_EVIDENCE = "missing_control_evidence"


@dataclass(frozen=True)
class ReconciliationResult:
    control_kind: ControlKind
    key: str
    source_amount: Decimal | None
    control_amount: Decimal | None
    variance: Decimal | None
    state: ReconciliationState
    source_evidence_ids: tuple[str, ...]
    control_evidence_sha256: str | None


def reconcile_amount(
    *,
    control_kind: ControlKind,
    key: str,
    source_amount: Decimal | None,
    control_amount: Decimal | None,
    source_evidence_ids: tuple[str, ...],
    control_evidence_sha256: str | None,
) -> ReconciliationResult:
    if source_amount is None:
        state = ReconciliationState.MISSING_SOURCE_EVIDENCE
        variance = None
    elif control_amount is None:
        state = ReconciliationState.MISSING_CONTROL_EVIDENCE
        variance = None
    else:
        variance = source_amount - control_amount
        state = (
            ReconciliationState.MATCHED
            if variance == Decimal(0)
            else ReconciliationState.EXCEPTION
        )
    return ReconciliationResult(
        control_kind=control_kind,
        key=key,
        source_amount=source_amount,
        control_amount=control_amount,
        variance=variance,
        state=state,
        source_evidence_ids=source_evidence_ids,
        control_evidence_sha256=control_evidence_sha256,
    )
