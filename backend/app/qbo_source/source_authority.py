from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum


class FactAuthority(str, Enum):
    HCP = "hcp_authoritative"
    QBO = "qbo_authoritative"
    ACP_NATIVE = "acp_native_authoritative"
    CORROBORATED = "corroborated"
    CONFLICTING = "conflicting"
    UNRESOLVED = "unresolved"


class CrossSourceDisposition(str, Enum):
    CORROBORATED = "corroborated"
    CONFLICTING_AMOUNT = "conflicting_amount"
    CONFLICTING_DATE = "conflicting_date"
    OPERATIONAL_ONLY = "operational_only"
    ACCOUNTING_ONLY = "accounting_only"
    MISSING_LINKAGE = "missing_linkage"


@dataclass(frozen=True)
class SourceFact:
    provider: str
    evidence_id: str
    fact_name: str
    canonical_value: str
    authoritative_link_id: str | None

    def __post_init__(self) -> None:
        if self.provider not in {"hcp", "qbo", "acp"}:
            raise ValueError("source provider is unsupported")
        if not self.evidence_id or not self.fact_name or not self.canonical_value:
            raise ValueError("complete source fact evidence is required")


@dataclass(frozen=True)
class CrossSourceFinding:
    disposition: CrossSourceDisposition
    authority: FactAuthority
    finding_digest: str


def reconcile_source_fact(
    *, hcp: SourceFact | None, qbo: SourceFact | None
) -> CrossSourceFinding:
    if hcp is None and qbo is None:
        raise ValueError("at least one source fact is required")
    if hcp is None:
        disposition = CrossSourceDisposition.ACCOUNTING_ONLY
        authority = FactAuthority.QBO
    elif qbo is None:
        disposition = CrossSourceDisposition.OPERATIONAL_ONLY
        authority = FactAuthority.HCP
    elif (
        hcp.authoritative_link_id is None
        or qbo.authoritative_link_id is None
        or hcp.authoritative_link_id != qbo.authoritative_link_id
        or hcp.fact_name != qbo.fact_name
    ):
        disposition = CrossSourceDisposition.MISSING_LINKAGE
        authority = FactAuthority.UNRESOLVED
    elif hcp.canonical_value == qbo.canonical_value:
        disposition = CrossSourceDisposition.CORROBORATED
        authority = FactAuthority.CORROBORATED
    else:
        disposition = (
            CrossSourceDisposition.CONFLICTING_DATE
            if "date" in hcp.fact_name
            else CrossSourceDisposition.CONFLICTING_AMOUNT
        )
        authority = FactAuthority.CONFLICTING
    canonical = {
        "authority": authority.value,
        "disposition": disposition.value,
        "hcp_evidence_id": hcp.evidence_id if hcp else None,
        "qbo_evidence_id": qbo.evidence_id if qbo else None,
        "fact_name": (hcp or qbo).fact_name,  # type: ignore[union-attr]
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CrossSourceFinding(
        disposition=disposition,
        authority=authority,
        finding_digest=digest,
    )
