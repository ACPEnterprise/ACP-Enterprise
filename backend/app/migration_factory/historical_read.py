"""Provider-neutral historical-read handoff contract for product consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class HistoricalDomain(StrEnum):
    CUSTOMER = "customer"
    LOCATION = "location"
    JOB = "job"
    APPOINTMENT = "appointment"
    ESTIMATE = "estimate"
    INVOICE = "invoice"
    PAYMENT = "payment"
    REFUND = "refund"
    ACCOUNTING_REPORT = "accounting_report"


class HistoricalAuthority(StrEnum):
    NATIVE = "NATIVE"
    SOURCE_BACKED = "SOURCE_BACKED"
    PROVISIONAL = "PROVISIONAL"
    DISCREPANCY = "DISCREPANCY"
    QUARANTINED = "QUARANTINED"


class CoverageDisposition(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_ACQUIRED = "NOT_ACQUIRED"


@dataclass(frozen=True, slots=True)
class HistoricalReadRequest:
    company_id: UUID
    start_date: date
    end_date: date
    domains: tuple[HistoricalDomain, ...]
    customer_id: UUID | None = None
    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("historical range is inverted")
        if not self.domains or len(self.domains) != len(set(self.domains)):
            raise ValueError("unique historical domains are required")
        if not 1 <= self.limit <= 500:
            raise ValueError("historical page limit must be between 1 and 500")


@dataclass(frozen=True, slots=True)
class HistoricalLineage:
    provider: str
    source_object_id: str
    evidence_digest: str
    acquired_at: datetime
    source_updated_at: datetime | None
    transformation_version: str

    def __post_init__(self) -> None:
        if len(self.evidence_digest) != 64:
            raise ValueError("historical evidence digest is invalid")
        if self.acquired_at.tzinfo is None:
            raise ValueError("historical acquisition time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class HistoricalRecord:
    domain: HistoricalDomain
    event_at: datetime | None
    canonical_id: UUID | None
    customer_id: UUID | None
    parent_references: tuple[str, ...]
    authority: HistoricalAuthority
    display: dict[str, object]
    lineage: HistoricalLineage
    aggregation_safe: bool

    def __post_init__(self) -> None:
        if self.event_at is not None and self.event_at.tzinfo is None:
            raise ValueError("historical event time must be timezone-aware")
        if (
            self.authority is not HistoricalAuthority.NATIVE
            and not self.lineage.provider
        ):
            raise ValueError("source-backed history requires provider lineage")


@dataclass(frozen=True, slots=True)
class DomainCoverage:
    domain: HistoricalDomain
    disposition: CoverageDisposition
    source_count: int | None
    returned_count: int
    unresolved_count: int
    as_of: datetime | None
    explanation: str | None = None

    def __post_init__(self) -> None:
        if min(self.returned_count, self.unresolved_count) < 0:
            raise ValueError("historical coverage counts cannot be negative")
        if self.source_count is not None and self.source_count < 0:
            raise ValueError("historical source count cannot be negative")
        if (
            self.disposition is not CoverageDisposition.COMPLETE
            and not self.explanation
        ):
            raise ValueError("incomplete historical coverage requires an explanation")


@dataclass(frozen=True, slots=True)
class HistoricalReadPage:
    contract_version: str
    company_id: UUID
    range_start: date
    range_end: date
    records: tuple[HistoricalRecord, ...]
    coverage: tuple[DomainCoverage, ...]
    next_cursor: str | None
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.contract_version != "twelvehats-historical-read/v1":
            raise ValueError("unsupported historical-read contract")
        if self.generated_at.tzinfo is None:
            raise ValueError("historical response time must be timezone-aware")
        ordered = sorted(
            self.records,
            key=lambda item: (
                item.event_at or item.lineage.acquired_at,
                item.domain.value,
                item.lineage.provider,
                item.lineage.source_object_id,
            ),
            reverse=True,
        )
        if list(self.records) != ordered:
            raise ValueError(
                "historical records require deterministic newest-first order"
            )


class AccountingReportKind(StrEnum):
    PROFIT_AND_LOSS = "profit_and_loss"
    BALANCE_SHEET = "balance_sheet"
    TRIAL_BALANCE = "trial_balance"
    GENERAL_LEDGER = "general_ledger"
    AR_AGING = "ar_aging"
    AP_AGING = "ap_aging"


@dataclass(frozen=True, slots=True)
class AccountingReportReadRequest:
    company_id: UUID
    kind: AccountingReportKind
    start_date: date | None
    end_date: date
    basis: str

    def __post_init__(self) -> None:
        if self.basis not in {"cash", "accrual"}:
            raise ValueError("accounting basis must be cash or accrual")
        if self.start_date is not None and self.start_date > self.end_date:
            raise ValueError("accounting report range is inverted")


@dataclass(frozen=True, slots=True)
class AccountingReportEvidence:
    contract_version: str
    request: AccountingReportReadRequest
    provider: str
    authority: HistoricalAuthority
    raw_digest: str
    registration_digest: str
    source_as_of: datetime | None
    payload: dict[str, object]
    accepted_as_native_accounting: bool = False

    def __post_init__(self) -> None:
        if self.contract_version != "twelvehats-accounting-report-read/v1":
            raise ValueError("unsupported accounting report contract")
        if len(self.raw_digest) != 64 or len(self.registration_digest) != 64:
            raise ValueError("accounting report evidence digest is invalid")
        if (
            self.authority is HistoricalAuthority.SOURCE_BACKED
            and self.accepted_as_native_accounting
        ):
            raise ValueError("source report cannot silently become native accounting")
