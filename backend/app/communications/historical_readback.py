"""Read-only reconciliation and scoped readback of historical communications."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .types import CommunicationChannel


class HistoricalCommunicationDisposition(StrEnum):
    READABLE = "READABLE"
    HELD_CONFLICT = "HELD_CONFLICT"
    HELD_MISSING_PROVENANCE = "HELD_MISSING_PROVENANCE"


@dataclass(frozen=True, slots=True)
class SourceHistoricalCommunication:
    provider: str
    source_id: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    occurred_at: datetime
    channel: CommunicationChannel
    direction: str
    display: str
    evidence_digest: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.source_id.strip():
            raise ValueError("communication source provenance is required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("communication timestamp must be timezone-aware")
        if self.direction not in {"inbound", "outbound"}:
            raise ValueError("communication direction is invalid")
        if len(self.evidence_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.evidence_digest
        ):
            raise ValueError("communication evidence digest is invalid")


@dataclass(frozen=True, slots=True)
class HistoricalCommunication:
    source_key: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    occurred_at: datetime
    channel: CommunicationChannel
    direction: str
    display: str | None
    evidence_digest: str
    disposition: HistoricalCommunicationDisposition
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class HistoricalCommunicationReconciliation:
    contract_version: str
    records: tuple[HistoricalCommunication, ...]
    reconciliation_digest: str


def _source_key(record: SourceHistoricalCommunication) -> str:
    return f"{record.provider.strip()}:{record.source_id.strip()}"


def reconcile_historical_communications(
    records: Iterable[SourceHistoricalCommunication],
) -> HistoricalCommunicationReconciliation:
    """Reconcile sealed evidence without delivery or provider-side activity."""
    grouped: dict[str, list[SourceHistoricalCommunication]] = {}
    for record in records:
        grouped.setdefault(_source_key(record), []).append(record)

    reconciled: list[HistoricalCommunication] = []
    for source_key in sorted(grouped):
        candidates = grouped[source_key]
        evidence = {candidate.evidence_digest for candidate in candidates}
        bindings = {
            (
                candidate.company_id,
                candidate.branch_id,
                candidate.customer_id,
                candidate.occurred_at,
                candidate.channel,
                candidate.direction,
                candidate.display,
            )
            for candidate in candidates
        }
        record = candidates[0]
        if len(evidence) != 1 or len(bindings) != 1:
            reconciled.append(
                HistoricalCommunication(
                    source_key,
                    record.company_id,
                    record.branch_id,
                    record.customer_id,
                    record.occurred_at,
                    record.channel,
                    record.direction,
                    None,
                    hashlib.sha256("|".join(sorted(evidence)).encode()).hexdigest(),
                    HistoricalCommunicationDisposition.HELD_CONFLICT,
                    "source identity has conflicting evidence or tenant binding",
                )
            )
            continue
        reconciled.append(
            HistoricalCommunication(
                source_key,
                record.company_id,
                record.branch_id,
                record.customer_id,
                record.occurred_at,
                record.channel,
                record.direction,
                record.display,
                record.evidence_digest,
                HistoricalCommunicationDisposition.READABLE,
            )
        )

    canonical = [
        {
            "source_key": item.source_key,
            "company_id": str(item.company_id),
            "branch_id": str(item.branch_id),
            "customer_id": str(item.customer_id),
            "occurred_at": item.occurred_at.isoformat(),
            "channel": item.channel.value,
            "direction": item.direction,
            "evidence_digest": item.evidence_digest,
            "disposition": item.disposition.value,
        }
        for item in reconciled
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return HistoricalCommunicationReconciliation(
        "twelvehats-historical-communications/v1", tuple(reconciled), digest
    )


def read_historical_communications(
    reconciliation: HistoricalCommunicationReconciliation,
    *,
    company_id: UUID,
    accessible_branch_ids: frozenset[UUID],
    branch_id: UUID | None = None,
    customer_id: UUID | None = None,
    limit: int = 50,
) -> tuple[HistoricalCommunication, ...]:
    """Return readable history within an already-authorized tenant scope."""
    if not 1 <= limit <= 200:
        raise ValueError("communication history limit must be between 1 and 200")
    if branch_id is not None and branch_id not in accessible_branch_ids:
        raise PermissionError("communication history branch access denied")
    records = (
        record
        for record in reconciliation.records
        if record.disposition is HistoricalCommunicationDisposition.READABLE
        and record.company_id == company_id
        and record.branch_id in accessible_branch_ids
        and (branch_id is None or record.branch_id == branch_id)
        and (customer_id is None or record.customer_id == customer_id)
    )
    return tuple(
        sorted(
            records, key=lambda item: (item.occurred_at, item.source_key), reverse=True
        )[:limit]
    )
