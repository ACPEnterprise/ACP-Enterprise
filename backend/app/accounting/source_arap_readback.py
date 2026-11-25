"""Read-only A/R and A/P projection from registered historical source records."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.source_history.registration import SourceRegistration

AccountKind = Literal["accounts_receivable", "accounts_payable"]


@dataclass(frozen=True, slots=True)
class SourceOpenItem:
    source_id: str
    account_kind: AccountKind
    counterparty_source_id: str
    counterparty_label: str
    transaction_date: str
    original_amount: Decimal
    open_amount: Decimal
    evidence_digest: str
    known_exception: str | None = None


@dataclass(frozen=True, slots=True)
class SourceTotal:
    account_kind: AccountKind
    open_amount: Decimal


@dataclass(frozen=True, slots=True)
class ArApReadback:
    registration_id: str
    provider: str
    items: tuple[SourceOpenItem, ...]
    calculated_totals: dict[AccountKind, Decimal]
    source_totals: dict[AccountKind, Decimal]
    exceptions: tuple[str, ...]
    read_only: bool = True
    admitted_as_native: bool = False
    mutation_authority: str = "none"


def project_source_arap(
    registration: SourceRegistration,
    items: tuple[SourceOpenItem, ...],
    source_totals: tuple[SourceTotal, ...],
) -> ArApReadback:
    """Validate and project source-backed open items without changing balances."""
    if not registration.read_only or registration.admitted_as_native:
        raise ValueError("source registration is not eligible for historical readback")
    if registration.provider.casefold() not in {
        "qbo",
        "quickbooks",
        "quickbooks_online",
    }:
        raise ValueError("source registration is not a QuickBooks source")

    calculated: dict[AccountKind, Decimal] = {
        "accounts_receivable": Decimal(0),
        "accounts_payable": Decimal(0),
    }
    reported: dict[AccountKind, Decimal] = {}
    exceptions: list[str] = []
    seen: set[tuple[AccountKind, str]] = set()

    for item in items:
        identity = (item.account_kind, item.source_id)
        if identity in seen:
            raise ValueError(f"duplicate source open item: {item.source_id}")
        seen.add(identity)
        if not item.source_id or not item.counterparty_source_id:
            raise ValueError("source and counterparty identifiers are required")
        if len(item.evidence_digest) != 64:
            raise ValueError(f"invalid evidence digest for {item.source_id}")
        if item.original_amount < 0 or item.open_amount < 0:
            raise ValueError(f"negative source balance for {item.source_id}")
        if item.open_amount > item.original_amount:
            exceptions.append(f"open amount exceeds original amount: {item.source_id}")
        calculated[item.account_kind] += item.open_amount
        if item.known_exception:
            exceptions.append(f"{item.source_id}: {item.known_exception}")

    for total in source_totals:
        if total.account_kind in reported:
            raise ValueError(f"duplicate source total: {total.account_kind}")
        if total.open_amount < 0:
            raise ValueError(f"negative source total: {total.account_kind}")
        reported[total.account_kind] = total.open_amount

    for account_kind, calculated_amount in calculated.items():
        if account_kind not in reported:
            exceptions.append(f"source total unavailable: {account_kind}")
        elif reported[account_kind] != calculated_amount:
            exceptions.append(
                "source total mismatch: "
                f"{account_kind} reported={reported[account_kind]} "
                f"calculated={calculated_amount}"
            )

    return ArApReadback(
        registration.registration_id,
        registration.provider,
        items,
        calculated,
        reported,
        tuple(exceptions),
    )
