from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class CustomerEvidenceClassification(StrEnum):
    CURRENT_AUTHORITATIVE = "CURRENT_AUTHORITATIVE"
    HISTORICAL_SOURCE_EVIDENCE = "HISTORICAL_SOURCE_EVIDENCE"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class CustomerSourceEvidence:
    company_id: str
    customer_id: str
    source_system: str
    source_record_identity: str | None
    as_of: date | None
    acquired_at: datetime | None
    evidence_digest: str | None
    completeness: str
    conflict_state: str
    classification: CustomerEvidenceClassification
    authority: str

    def as_dict(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "customer_id": self.customer_id,
            "source_system": self.source_system,
            "source_record_identity": self.source_record_identity,
            "as_of": self.as_of,
            "acquired_at": self.acquired_at,
            "evidence_digest": self.evidence_digest,
            "completeness": self.completeness,
            "conflict_state": self.conflict_state,
            "classification": self.classification.value,
            "authority": self.authority,
        }


def native_evidence(
    *,
    company_id: str,
    customer_id: str,
    as_of: date,
    acquired_at: datetime | None,
    values: dict[str, object],
    partial: bool,
    conflicting: bool,
) -> CustomerSourceEvidence:
    document = {"company_id": company_id, "customer_id": customer_id, "as_of": as_of.isoformat(), **values}
    digest = hashlib.sha256(
        json.dumps(
            document, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    classification = (
        CustomerEvidenceClassification.CONFLICTING
        if conflicting
        else CustomerEvidenceClassification.PARTIAL
        if partial
        else CustomerEvidenceClassification.CURRENT_AUTHORITATIVE
    )
    return CustomerSourceEvidence(
        company_id=company_id,
        customer_id=customer_id,
        source_system="acp_native",
        source_record_identity=customer_id,
        as_of=as_of,
        acquired_at=acquired_at,
        evidence_digest=digest,
        completeness="partial" if partial else "complete",
        conflict_state="conflicting" if conflicting else "none",
        classification=classification,
        authority="native_invoice_and_receipt_authority",
    )


def historical_source_evidence(
    *,
    company_id: str,
    customer_id: str,
    source_system: str,
    source_record_identity: str,
    acquired_at: datetime | None,
    evidence_digest: str | None,
    complete: bool,
    conflicting: bool = False,
    stale: bool = False,
    as_of: date | None = None,
) -> CustomerSourceEvidence:
    classification = (
        CustomerEvidenceClassification.CONFLICTING
        if conflicting
        else CustomerEvidenceClassification.STALE
        if stale
        else CustomerEvidenceClassification.PARTIAL
        if not complete
        else CustomerEvidenceClassification.HISTORICAL_SOURCE_EVIDENCE
    )
    return CustomerSourceEvidence(
        company_id=company_id,
        customer_id=customer_id,
        source_system=source_system,
        source_record_identity=source_record_identity,
        as_of=as_of,
        acquired_at=acquired_at,
        evidence_digest=evidence_digest,
        completeness="complete" if complete else "partial",
        conflict_state="conflicting" if conflicting else "none",
        classification=classification,
        authority="historical_source_evidence_only",
    )


def unavailable_source_evidence(
    *,
    company_id: str,
    customer_id: str,
    source_system: str = "external_source",
) -> CustomerSourceEvidence:
    return CustomerSourceEvidence(
        company_id=company_id,
        customer_id=customer_id,
        source_system=source_system,
        source_record_identity=None,
        as_of=None,
        acquired_at=None,
        evidence_digest=None,
        completeness="unavailable",
        conflict_state="unknown",
        classification=CustomerEvidenceClassification.UNAVAILABLE,
        authority="none",
    )
