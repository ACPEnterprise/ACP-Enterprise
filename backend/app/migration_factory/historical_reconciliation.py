"""Deterministic, read-only reconciliation for provider historical records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .historical_read import HistoricalDomain


class ReconciliationDisposition(StrEnum):
    PROJECTED = "PROJECTED"
    HELD_MISSING_PARENT = "HELD_MISSING_PARENT"
    HELD_CONFLICT = "HELD_CONFLICT"


@dataclass(frozen=True, slots=True)
class SourceHistoryRecord:
    domain: HistoricalDomain
    source_id: str
    source_updated_at: datetime | None
    parent_source_ids: tuple[str, ...]
    payload: Mapping[str, object]
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source history identity is required")
        if len(self.evidence_digest) != 64:
            raise ValueError("source history evidence digest is invalid")
        if self.source_updated_at is not None and self.source_updated_at.tzinfo is None:
            raise ValueError("source history timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ReconciledHistoryRecord:
    source_key: str
    disposition: ReconciliationDisposition
    parent_source_keys: tuple[str, ...]
    payload: Mapping[str, object] | None
    evidence_digest: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class HistoricalReconciliation:
    contract_version: str
    provider: str
    records: tuple[ReconciledHistoryRecord, ...]
    reconciliation_digest: str


_ROOT_DOMAINS = {HistoricalDomain.CUSTOMER}


def _key(domain: HistoricalDomain, source_id: str) -> str:
    return f"{domain.value}:{source_id}"


def reconcile_history(
    provider: str, records: Iterable[SourceHistoryRecord]
) -> HistoricalReconciliation:
    """Reconcile a sealed source graph without inventing identities or parents."""
    if not provider.strip():
        raise ValueError("history provider is required")
    grouped: dict[str, list[SourceHistoryRecord]] = {}
    for record in records:
        grouped.setdefault(_key(record.domain, record.source_id), []).append(record)

    known_ids = set(grouped)
    output: list[ReconciledHistoryRecord] = []
    for source_key in sorted(grouped):
        candidates = grouped[source_key]
        digests = {item.evidence_digest for item in candidates}
        if len(digests) != 1:
            output.append(
                ReconciledHistoryRecord(
                    source_key,
                    ReconciliationDisposition.HELD_CONFLICT,
                    (),
                    None,
                    hashlib.sha256("|".join(sorted(digests)).encode()).hexdigest(),
                    "source identity has conflicting evidence",
                )
            )
            continue
        record = candidates[0]
        parent_keys = tuple(sorted(set(record.parent_source_ids)))
        missing = tuple(parent for parent in parent_keys if parent not in known_ids)
        if record.domain not in _ROOT_DOMAINS and (not parent_keys or missing):
            reason = (
                "missing required parent"
                if not parent_keys
                else "unresolved parent: " + ",".join(missing)
            )
            output.append(
                ReconciledHistoryRecord(
                    source_key,
                    ReconciliationDisposition.HELD_MISSING_PARENT,
                    parent_keys,
                    None,
                    record.evidence_digest,
                    reason,
                )
            )
            continue
        output.append(
            ReconciledHistoryRecord(
                source_key,
                ReconciliationDisposition.PROJECTED,
                parent_keys,
                dict(record.payload),
                record.evidence_digest,
            )
        )

    canonical = [
        {
            "source_key": item.source_key,
            "disposition": item.disposition.value,
            "parents": item.parent_source_keys,
            "evidence_digest": item.evidence_digest,
            "reason": item.reason,
        }
        for item in output
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return HistoricalReconciliation(
        "twelvehats-historical-reconciliation/v1", provider, tuple(output), digest
    )
