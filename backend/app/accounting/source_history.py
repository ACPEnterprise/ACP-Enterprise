"""Read-only, source-backed accounting history projection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class FinancialHistoryDisposition(StrEnum):
    SOURCE_BACKED = "SOURCE_BACKED"
    HELD_MISSING_RELATIONSHIP = "HELD_MISSING_RELATIONSHIP"
    HELD_CONFLICT = "HELD_CONFLICT"


@dataclass(frozen=True, slots=True)
class FinancialSourceRecord:
    source_type: str
    source_id: str
    accounting_date: date
    amount: Decimal
    currency: str
    related_source_keys: tuple[str, ...]
    source_payload: Mapping[str, object]
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.source_type.strip() or not self.source_id.strip():
            raise ValueError("financial source identity is required")
        if len(self.evidence_digest) != 64:
            raise ValueError("financial source evidence digest is invalid")
        if not self.currency.strip():
            raise ValueError("financial source currency is required")

    @property
    def source_key(self) -> str:
        return f"{self.source_type}:{self.source_id}"


@dataclass(frozen=True, slots=True)
class FinancialHistoryItem:
    source_key: str
    accounting_date: date
    amount: Decimal
    currency: str
    related_source_keys: tuple[str, ...]
    disposition: FinancialHistoryDisposition
    source_payload: Mapping[str, object] | None
    evidence_digest: str
    exception: str | None = None
    accepted_as_native: bool = False


@dataclass(frozen=True, slots=True)
class FinancialHistoryProjection:
    contract_version: str
    provider: str
    items: tuple[FinancialHistoryItem, ...]
    projection_digest: str
    read_only: bool = True


def project_financial_history(
    provider: str, records: Iterable[FinancialSourceRecord]
) -> FinancialHistoryProjection:
    """Project source facts without posting, classifying, or repairing them."""
    if not provider.strip():
        raise ValueError("financial history provider is required")
    grouped: dict[str, list[FinancialSourceRecord]] = {}
    for record in records:
        grouped.setdefault(record.source_key, []).append(record)
    known = set(grouped)
    items: list[FinancialHistoryItem] = []
    for source_key in sorted(grouped):
        candidates = grouped[source_key]
        evidence = {item.evidence_digest for item in candidates}
        record = candidates[0]
        related = tuple(sorted(set(record.related_source_keys)))
        if len(evidence) != 1:
            items.append(
                FinancialHistoryItem(
                    source_key,
                    record.accounting_date,
                    record.amount,
                    record.currency,
                    related,
                    FinancialHistoryDisposition.HELD_CONFLICT,
                    None,
                    hashlib.sha256("|".join(sorted(evidence)).encode()).hexdigest(),
                    "source identity has conflicting evidence",
                )
            )
            continue
        missing = tuple(key for key in related if key not in known)
        if missing:
            items.append(
                FinancialHistoryItem(
                    source_key,
                    record.accounting_date,
                    record.amount,
                    record.currency,
                    related,
                    FinancialHistoryDisposition.HELD_MISSING_RELATIONSHIP,
                    None,
                    record.evidence_digest,
                    "unresolved source relationship: " + ",".join(missing),
                )
            )
            continue
        items.append(
            FinancialHistoryItem(
                source_key,
                record.accounting_date,
                record.amount,
                record.currency,
                related,
                FinancialHistoryDisposition.SOURCE_BACKED,
                dict(record.source_payload),
                record.evidence_digest,
            )
        )
    canonical = [
        {
            "source_key": item.source_key,
            "date": item.accounting_date.isoformat(),
            "amount": str(item.amount),
            "currency": item.currency,
            "relationships": item.related_source_keys,
            "disposition": item.disposition.value,
            "evidence_digest": item.evidence_digest,
            "exception": item.exception,
        }
        for item in items
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return FinancialHistoryProjection(
        "twelvehats-financial-source-history/v1",
        provider,
        tuple(items),
        digest,
    )
