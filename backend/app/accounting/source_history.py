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


class FinancialReportDisposition(StrEnum):
    SOURCE_BACKED = "SOURCE_BACKED"
    HELD_MISSING_RELATIONSHIP = "HELD_MISSING_RELATIONSHIP"
    HELD_SOURCE_EXCEPTION = "HELD_SOURCE_EXCEPTION"
    HELD_TOTAL_MISMATCH = "HELD_TOTAL_MISMATCH"


@dataclass(frozen=True, slots=True)
class FinancialReportSourceRecord:
    report_kind: str
    source_id: str
    start_date: date | None
    end_date: date
    basis: str
    currency: str
    account_totals: tuple[tuple[str, Decimal], ...]
    reported_total: Decimal
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.report_kind.strip() or not self.source_id.strip():
            raise ValueError("financial report source identity is required")
        if self.start_date is not None and self.start_date > self.end_date:
            raise ValueError("financial report date range is inverted")
        if self.basis not in {"cash", "accrual"}:
            raise ValueError("financial report basis is invalid")
        if not self.currency.strip():
            raise ValueError("financial report currency is required")
        if len(self.evidence_digest) != 64:
            raise ValueError("financial report evidence digest is invalid")
        account_keys = tuple(key for key, _amount in self.account_totals)
        if not account_keys or len(account_keys) != len(set(account_keys)):
            raise ValueError("financial report account relationships must be unique")

    @property
    def source_key(self) -> str:
        return f"Report:{self.report_kind}:{self.source_id}"


@dataclass(frozen=True, slots=True)
class FinancialReportReadback:
    source_key: str
    report_kind: str
    start_date: date | None
    end_date: date
    basis: str
    currency: str
    account_totals: tuple[tuple[str, Decimal], ...]
    reported_total: Decimal
    relationship_total: Decimal
    disposition: FinancialReportDisposition
    evidence_digest: str
    exception: str | None = None
    accepted_as_native: bool = False


@dataclass(frozen=True, slots=True)
class FinancialReportProjection:
    contract_version: str
    provider: str
    reports: tuple[FinancialReportReadback, ...]
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


def project_financial_reports(
    history: FinancialHistoryProjection,
    reports: Iterable[FinancialReportSourceRecord],
) -> FinancialReportProjection:
    """Project sealed report totals without posting or repairing exceptions."""
    history_by_key = {item.source_key: item for item in history.items}
    grouped: dict[str, list[FinancialReportSourceRecord]] = {}
    for report in reports:
        grouped.setdefault(report.source_key, []).append(report)

    output: list[FinancialReportReadback] = []
    for source_key in sorted(grouped):
        candidates = grouped[source_key]
        digests = {candidate.evidence_digest for candidate in candidates}
        report = candidates[0]
        account_totals = tuple(sorted(report.account_totals))
        relationship_total = sum(
            (amount for _account_key, amount in account_totals), Decimal(0)
        )
        missing = tuple(
            account_key
            for account_key, _amount in account_totals
            if account_key not in history_by_key
        )
        held = tuple(
            account_key
            for account_key, _amount in account_totals
            if account_key in history_by_key
            and history_by_key[account_key].disposition
            is not FinancialHistoryDisposition.SOURCE_BACKED
        )
        if len(digests) != 1:
            disposition = FinancialReportDisposition.HELD_SOURCE_EXCEPTION
            exception = "report source identity has conflicting evidence"
        elif missing:
            disposition = FinancialReportDisposition.HELD_MISSING_RELATIONSHIP
            exception = "unresolved report account relationship: " + ",".join(missing)
        elif held:
            disposition = FinancialReportDisposition.HELD_SOURCE_EXCEPTION
            exception = "report account relationship is held: " + ",".join(held)
        elif relationship_total != report.reported_total:
            disposition = FinancialReportDisposition.HELD_TOTAL_MISMATCH
            exception = "source report total does not agree with relationship totals"
        else:
            disposition = FinancialReportDisposition.SOURCE_BACKED
            exception = None
        output.append(
            FinancialReportReadback(
                source_key,
                report.report_kind,
                report.start_date,
                report.end_date,
                report.basis,
                report.currency,
                account_totals,
                report.reported_total,
                relationship_total,
                disposition,
                report.evidence_digest,
                exception,
            )
        )

    canonical = [
        {
            "source_key": item.source_key,
            "kind": item.report_kind,
            "start_date": item.start_date.isoformat() if item.start_date else None,
            "end_date": item.end_date.isoformat(),
            "basis": item.basis,
            "currency": item.currency,
            "account_totals": tuple(
                (key, str(amount)) for key, amount in item.account_totals
            ),
            "reported_total": str(item.reported_total),
            "relationship_total": str(item.relationship_total),
            "disposition": item.disposition.value,
            "evidence_digest": item.evidence_digest,
            "exception": item.exception,
        }
        for item in output
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return FinancialReportProjection(
        "twelvehats-financial-report-readback/v1",
        history.provider,
        tuple(output),
        digest,
    )
