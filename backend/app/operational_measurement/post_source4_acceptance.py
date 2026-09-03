"""Cross-domain post-SOURCE.4 acceptance over admitted read-only projections."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.operational_measurement.realdata_acceptance import (
    AcceptanceClassification,
    OperationalAcceptanceReport,
)

CONTRACT_VERSION: Final = "operations.crossdomain.post-source4.acceptance.v1"
MAX_COMMERCIAL_RECORDS: Final = 10_000


class CommercialDomain(StrEnum):
    ESTIMATE = "ESTIMATE"
    INVOICE_AR = "INVOICE_AR"


@dataclass(frozen=True, slots=True)
class EstimateAcceptanceProjection:
    source_id: str
    source_digest: str
    source_job_id: str
    native_id: UUID | None
    native_job_id: UUID | None
    company_id: UUID
    branch_id: UUID
    customer_id: UUID | None
    service_location_id: UUID | None
    status: str | None
    accepted_snapshot_digest: str | None
    native_evidence_digest: str | None


@dataclass(frozen=True, slots=True)
class InvoiceARAcceptanceProjection:
    source_id: str
    source_digest: str
    source_job_id: str
    source_estimate_id: str | None
    native_id: UUID | None
    native_job_id: UUID | None
    native_estimate_id: UUID | None
    company_id: UUID
    branch_id: UUID
    customer_id: UUID | None
    service_location_id: UUID | None
    currency: str | None
    total_amount: Decimal | None
    open_amount: Decimal | None
    status: str | None
    line_evidence_complete: bool
    native_evidence_digest: str | None


@dataclass(frozen=True, slots=True)
class CommercialAcceptanceFinding:
    domain: CommercialDomain
    source_id: str
    classification: AcceptanceClassification
    conditions: tuple[str, ...]
    source_digest: str
    native_digest: str | None


@dataclass(frozen=True, slots=True)
class CrossDomainAcceptanceReport:
    contract_version: str
    company_id: UUID
    branch_id: UUID
    operational_report_digest: str
    operational_counts: dict[str, int]
    commercial_findings: tuple[CommercialAcceptanceFinding, ...]
    commercial_counts: dict[str, int]
    evidence_digest: str
    mutation_authority: str = "none"


def _digest(value: object) -> str:
    def default(item: object) -> str:
        if isinstance(item, (UUID, Decimal, StrEnum)):
            return str(item)
        raise TypeError(f"unsupported digest value: {type(item).__name__}")

    return hashlib.sha256(
        json.dumps(
            value,
            default=default,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _scope_conditions(company_id: UUID, branch_id: UUID, *, expected_company_id: UUID, expected_branch_id: UUID) -> list[str]:
    return [] if (company_id, branch_id) == (expected_company_id, expected_branch_id) else ["COMPANY_OR_BRANCH_SCOPE_CONFLICT"]


def _estimate_findings(
    estimates: tuple[EstimateAcceptanceProjection, ...],
    *,
    company_id: UUID,
    branch_id: UUID,
    operational_job_sources: frozenset[str],
) -> tuple[CommercialAcceptanceFinding, ...]:
    grouped: dict[str, list[EstimateAcceptanceProjection]] = {}
    for item in estimates:
        grouped.setdefault(item.source_id, []).append(item)
    findings: list[CommercialAcceptanceFinding] = []
    for source_id in sorted(grouped):
        rows = grouped[source_id]
        row = min(rows, key=lambda item: (item.source_digest, item.native_evidence_digest or ""))
        conditions = _scope_conditions(row.company_id, row.branch_id, expected_company_id=company_id, expected_branch_id=branch_id)
        classification = AcceptanceClassification.MATCHED
        if len(rows) > 1:
            conditions.append("DUPLICATE_NATIVE_SOURCE_IDENTITY")
            classification = AcceptanceClassification.CONFLICTING
        elif conditions:
            classification = AcceptanceClassification.CONFLICTING
        elif row.native_id is None or row.native_job_id is None or row.native_evidence_digest is None:
            conditions.append("NATIVE_ESTIMATE_OR_JOB_IDENTITY_MISSING")
            classification = AcceptanceClassification.MISSING_NATIVE
        elif row.source_job_id not in operational_job_sources:
            conditions.append("JOB_SOURCE_LINEAGE_MISSING")
            classification = AcceptanceClassification.ORPHANED
        elif row.customer_id is None or row.service_location_id is None:
            conditions.append("CUSTOMER_OR_LOCATION_EVIDENCE_MISSING")
            classification = AcceptanceClassification.ORPHANED
        elif row.status is None or row.accepted_snapshot_digest is None:
            conditions.append("COMMERCIAL_SOURCE_EVIDENCE_PARTIAL")
            classification = AcceptanceClassification.PARTIAL
        findings.append(CommercialAcceptanceFinding(CommercialDomain.ESTIMATE, source_id, classification, tuple(sorted(set(conditions))), row.source_digest, row.native_evidence_digest))
    return tuple(findings)


def _invoice_findings(
    invoices: tuple[InvoiceARAcceptanceProjection, ...],
    estimates: tuple[EstimateAcceptanceProjection, ...],
    *,
    company_id: UUID,
    branch_id: UUID,
    operational_job_sources: frozenset[str],
) -> tuple[CommercialAcceptanceFinding, ...]:
    grouped: dict[str, list[InvoiceARAcceptanceProjection]] = {}
    for item in invoices:
        grouped.setdefault(item.source_id, []).append(item)
    estimates_by_source = {item.source_id: item for item in estimates}
    findings: list[CommercialAcceptanceFinding] = []
    for source_id in sorted(grouped):
        rows = grouped[source_id]
        row = min(rows, key=lambda item: (item.source_digest, item.native_evidence_digest or ""))
        conditions = _scope_conditions(row.company_id, row.branch_id, expected_company_id=company_id, expected_branch_id=branch_id)
        classification = AcceptanceClassification.MATCHED
        if len(rows) > 1:
            conditions.append("DUPLICATE_NATIVE_SOURCE_IDENTITY")
            classification = AcceptanceClassification.CONFLICTING
        elif conditions:
            classification = AcceptanceClassification.CONFLICTING
        elif row.native_id is None or row.native_job_id is None or row.native_evidence_digest is None:
            conditions.append("NATIVE_INVOICE_OR_JOB_IDENTITY_MISSING")
            classification = AcceptanceClassification.MISSING_NATIVE
        elif row.source_job_id not in operational_job_sources:
            conditions.append("JOB_SOURCE_LINEAGE_MISSING")
            classification = AcceptanceClassification.ORPHANED
        elif row.customer_id is None or row.service_location_id is None:
            conditions.append("CUSTOMER_OR_LOCATION_EVIDENCE_MISSING")
            classification = AcceptanceClassification.ORPHANED
        elif row.source_estimate_id is not None:
            estimate = estimates_by_source.get(row.source_estimate_id)
            if estimate is None:
                conditions.append("ESTIMATE_SOURCE_LINEAGE_MISSING")
                classification = AcceptanceClassification.ORPHANED
            elif row.native_estimate_id != estimate.native_id:
                conditions.append("ESTIMATE_RELATIONSHIP_CONFLICT")
                classification = AcceptanceClassification.CONFLICTING
            elif row.source_job_id != estimate.source_job_id or row.native_job_id != estimate.native_job_id:
                conditions.append("JOB_RELATIONSHIP_CONFLICT")
                classification = AcceptanceClassification.CONFLICTING
        if (row.total_amount is not None and row.total_amount < 0) or (
            row.open_amount is not None and row.open_amount < 0
        ):
            conditions.append("INVALID_AR_AMOUNT")
            classification = AcceptanceClassification.CONFLICTING
        elif row.total_amount is not None and row.open_amount is not None and row.open_amount > row.total_amount:
            conditions.append("OPEN_BALANCE_EXCEEDS_INVOICE")
            classification = AcceptanceClassification.CONFLICTING
        elif classification is AcceptanceClassification.MATCHED and (
            row.currency is None or row.total_amount is None or row.open_amount is None or row.status is None or not row.line_evidence_complete
        ):
            conditions.append("INVOICE_AR_SOURCE_EVIDENCE_PARTIAL")
            classification = AcceptanceClassification.PARTIAL
        findings.append(CommercialAcceptanceFinding(CommercialDomain.INVOICE_AR, source_id, classification, tuple(sorted(set(conditions))), row.source_digest, row.native_evidence_digest))
    return tuple(findings)


def verify_cross_domain_chain(
    operational_report: OperationalAcceptanceReport,
    estimates: tuple[EstimateAcceptanceProjection, ...],
    invoices: tuple[InvoiceARAcceptanceProjection, ...],
    *,
    company_id: UUID,
    branch_id: UUID,
) -> CrossDomainAcceptanceReport:
    if len(estimates) > MAX_COMMERCIAL_RECORDS or len(invoices) > MAX_COMMERCIAL_RECORDS:
        raise ValueError("commercial acceptance input exceeds its bound")
    if operational_report.company_id != company_id or operational_report.branch_id != branch_id:
        raise ValueError("operational acceptance scope does not match commercial scope")
    operational_job_sources = frozenset(
        item.source_id for item in operational_report.findings if item.stage == "LINEAGE" and item.domain == "JOB"
    )
    findings = tuple(sorted((*_estimate_findings(estimates, company_id=company_id, branch_id=branch_id, operational_job_sources=operational_job_sources), *_invoice_findings(invoices, estimates, company_id=company_id, branch_id=branch_id, operational_job_sources=operational_job_sources)), key=lambda item: (item.domain.value, item.source_id)))
    counts = dict(sorted(Counter(item.classification.value for item in findings).items()))
    digest = _digest({"contract": CONTRACT_VERSION, "operational_report_digest": operational_report.evidence_digest, "findings": [asdict(item) for item in findings]})
    return CrossDomainAcceptanceReport(CONTRACT_VERSION, company_id, branch_id, operational_report.evidence_digest, operational_report.counts, findings, counts, digest)
