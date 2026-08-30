"""Deterministic Payroll reporting and provider-neutral filing evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

REPORTING_VERSION = "payroll.reporting.v1"
FILING_PACKAGE_VERSION = "payroll.filing-package.v1"


class ReportingError(ValueError):
    pass


class ReportingState(StrEnum):
    AUTHORITATIVE = "authoritative"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    CONFLICTING = "conflicting"


class ReportingPeriodKind(StrEnum):
    PAY_PERIOD = "pay_period"
    QUARTER = "quarter"
    YEAR = "year"


@dataclass(frozen=True, slots=True)
class ReportingPeriod:
    identity: str
    kind: ReportingPeriodKind
    start: date
    end: date

    def __post_init__(self) -> None:
        if not self.identity or self.end < self.start:
            raise ReportingError("reporting period identity and interval are required")


@dataclass(frozen=True, slots=True)
class HistoryCoverageEvidence:
    evidence_id: str
    evidence_digest: str
    company_id: UUID
    start: date
    end: date
    accepted: bool
    complete: bool
    source_authority: str


@dataclass(frozen=True, slots=True)
class PayrollReportingSource:
    source_id: str
    source_digest: str
    company_id: UUID
    employee_id: UUID
    period_id: UUID
    effective_date: date
    currency: str
    gross: Decimal
    employee_taxes: Decimal
    employer_taxes_contributions: Decimal
    employee_deductions: Decimal
    net_pay: Decimal
    approved: bool
    active: bool
    off_cycle: bool = False
    adjustment_id: str | None = None
    payment_status: str = "not_available"
    remittance_status: str = "not_available"

    def __post_init__(self) -> None:
        if not self.source_id or not _digest_valid(self.source_digest):
            raise ReportingError("immutable Payroll source identity is required")
        if len(self.currency) != 3 or any(
            value < 0
            for value in (
                self.gross,
                self.employee_taxes,
                self.employer_taxes_contributions,
                self.employee_deductions,
                self.net_pay,
            )
        ):
            raise ReportingError("Payroll source money is invalid")
        if self.gross - self.employee_taxes - self.employee_deductions != self.net_pay:
            raise ReportingError("Payroll source does not reconcile to net pay")


@dataclass(frozen=True, slots=True)
class ReportingTotals:
    gross: Decimal
    employee_taxes: Decimal
    employer_taxes_contributions: Decimal
    employee_deductions: Decimal
    net_pay: Decimal


@dataclass(frozen=True, slots=True)
class PayrollReportingResult:
    report_id: str
    report_digest: str
    company_id: UUID
    employee_id: UUID | None
    period: ReportingPeriod
    currency: str | None
    state: ReportingState
    totals: ReportingTotals | None
    source_ids: tuple[str, ...]
    source_digests: tuple[str, ...]
    coverage_evidence_id: str | None
    blockers: tuple[str, ...]
    reconciliation_digest: str
    version: str = REPORTING_VERSION


class PayrollReportingEngine:
    def compose(
        self,
        *,
        company_id: UUID,
        period: ReportingPeriod,
        sources: tuple[PayrollReportingSource, ...],
        coverage: HistoryCoverageEvidence | None,
        employee_id: UUID | None = None,
    ) -> PayrollReportingResult:
        relevant = tuple(
            sorted(
                (
                    item
                    for item in sources
                    if period.start <= item.effective_date <= period.end
                    and (employee_id is None or item.employee_id == employee_id)
                ),
                key=lambda item: item.source_id,
            )
        )
        blockers: list[str] = []
        if any(item.company_id != company_id for item in relevant):
            raise ReportingError("cross-Company Payroll reporting evidence")
        if len({item.source_id for item in relevant}) != len(relevant):
            raise ReportingError("duplicate Payroll reporting source identity")
        if any(not item.approved for item in relevant):
            blockers.append("UNAPPROVED_SOURCE")
        if any(not item.active for item in relevant):
            blockers.append("SUPERSEDED_SOURCE")
        currencies = {item.currency for item in relevant}
        if len(currencies) > 1:
            blockers.append("CURRENCY_CONFLICT")
        coverage_complete = bool(
            coverage
            and coverage.company_id == company_id
            and coverage.accepted
            and coverage.complete
            and coverage.start <= period.start
            and coverage.end >= period.end
            and _digest_valid(coverage.evidence_digest)
        )
        if coverage is not None and coverage.company_id != company_id:
            raise ReportingError("cross-Company historical coverage evidence")
        if not coverage_complete:
            blockers.append("HISTORY_INCOMPLETE")
        if not relevant:
            blockers.append("NO_ACCEPTED_PAYROLL_RESULTS")

        if "CURRENCY_CONFLICT" in blockers or "SUPERSEDED_SOURCE" in blockers:
            state = ReportingState.CONFLICTING
        elif not relevant:
            state = ReportingState.UNAVAILABLE
        elif blockers:
            state = ReportingState.PARTIAL
        else:
            state = ReportingState.AUTHORITATIVE
        totals = self._totals(relevant) if relevant else None
        canonical = {
            "version": REPORTING_VERSION,
            "company_id": str(company_id),
            "employee_id": str(employee_id) if employee_id else None,
            "period": {
                "identity": period.identity,
                "kind": period.kind.value,
                "start": period.start.isoformat(),
                "end": period.end.isoformat(),
            },
            "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "state": state.value,
            "totals": _totals_document(totals),
            "sources": [
                {
                    "id": item.source_id,
                    "digest": item.source_digest,
                    "off_cycle": item.off_cycle,
                    "adjustment_id": item.adjustment_id,
                    "payment_status": item.payment_status,
                    "remittance_status": item.remittance_status,
                }
                for item in relevant
            ],
            "coverage": {"id": coverage.evidence_id, "digest": coverage.evidence_digest}
            if coverage
            else None,
            "blockers": sorted(set(blockers)),
        }
        digest = _digest(canonical)
        reconciliation = _digest(
            {
                "source_digests": [item.source_digest for item in relevant],
                "totals": _totals_document(totals),
                "gross_less_employee_items_equals_net": bool(
                    totals
                    and totals.gross
                    - totals.employee_taxes
                    - totals.employee_deductions
                    == totals.net_pay
                ),
            }
        )
        return PayrollReportingResult(
            report_id=f"payroll-report:{digest}",
            report_digest=digest,
            company_id=company_id,
            employee_id=employee_id,
            period=period,
            currency=canonical["currency"]
            if isinstance(canonical["currency"], str)
            else None,
            state=state,
            totals=totals,
            source_ids=tuple(item.source_id for item in relevant),
            source_digests=tuple(item.source_digest for item in relevant),
            coverage_evidence_id=coverage.evidence_id if coverage else None,
            blockers=tuple(sorted(set(blockers))),
            reconciliation_digest=reconciliation,
        )

    @staticmethod
    def _totals(values: tuple[PayrollReportingSource, ...]) -> ReportingTotals:
        return ReportingTotals(
            *(
                sum((getattr(item, field) for item in values), Decimal(0))
                for field in (
                    "gross",
                    "employee_taxes",
                    "employer_taxes_contributions",
                    "employee_deductions",
                    "net_pay",
                )
            )
        )


@dataclass(frozen=True, slots=True)
class FilingConfigurationAuthority:
    authority_id: str
    authority_digest: str
    company_id: UUID
    jurisdiction_reference: str
    package_type: str
    schema_version: str
    effective_start: date
    effective_end: date | None
    approved: bool
    synthetic: bool = False


@dataclass(frozen=True, slots=True)
class FilingPackageEvidence:
    package_id: str
    package_digest: str
    company_id: UUID
    reporting_result_id: str
    reporting_result_digest: str
    configuration_id: str
    jurisdiction_reference: str
    package_type: str
    schema_version: str
    state: str
    payload_digest: str
    version: str = FILING_PACKAGE_VERSION


def prepare_filing_package(
    *, result: PayrollReportingResult, authority: FilingConfigurationAuthority
) -> FilingPackageEvidence:
    if result.state is not ReportingState.AUTHORITATIVE:
        raise ReportingError("authoritative complete reporting evidence is required")
    if (
        authority.company_id != result.company_id
        or not authority.approved
        or not _digest_valid(authority.authority_digest)
    ):
        raise ReportingError("approved Company filing configuration is required")
    if not (
        authority.effective_start <= result.period.end
        and (
            authority.effective_end is None
            or authority.effective_end >= result.period.start
        )
    ):
        raise ReportingError("filing configuration does not cover reporting period")
    payload = {
        "report_id": result.report_id,
        "report_digest": result.report_digest,
        "configuration_id": authority.authority_id,
        "configuration_digest": authority.authority_digest,
        "jurisdiction_reference": authority.jurisdiction_reference,
        "package_type": authority.package_type,
        "schema_version": authority.schema_version,
    }
    payload_digest = _digest(payload)
    package_digest = _digest(
        {"version": FILING_PACKAGE_VERSION, **payload, "payload_digest": payload_digest}
    )
    return FilingPackageEvidence(
        package_id=f"payroll-filing-package:{package_digest}",
        package_digest=package_digest,
        company_id=result.company_id,
        reporting_result_id=result.report_id,
        reporting_result_digest=result.report_digest,
        configuration_id=authority.authority_id,
        jurisdiction_reference=authority.jurisdiction_reference,
        package_type=authority.package_type,
        schema_version=authority.schema_version,
        state="prepared_not_submitted",
        payload_digest=payload_digest,
    )


def _totals_document(value: ReportingTotals | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {
        field: str(getattr(value, field))
        for field in (
            "gross",
            "employee_taxes",
            "employer_taxes_contributions",
            "employee_deductions",
            "net_pay",
        )
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _digest_valid(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
