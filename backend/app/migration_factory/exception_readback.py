"""Administrator readback for held reconciliation evidence; never a merge path."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class HeldSourceException:
    company_id: UUID
    branch_id: UUID
    source_key: str
    exception_type: str
    explanation: str
    evidence_digest: str
    related_source_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.exception_type not in {
            "AMBIGUOUS_IDENTITY",
            "MISSING_PARENT",
            "SOURCE_VERSION_CONFLICT",
        }:
            raise ValueError("unsupported reconciliation exception type")
        if not self.source_key.strip() or not self.explanation.strip():
            raise ValueError("reconciliation exception evidence is incomplete")
        if len(self.evidence_digest) != 64:
            raise ValueError("reconciliation exception digest is invalid")


@dataclass(frozen=True, slots=True)
class ReconciliationExceptionItem:
    exception_id: str
    source_key: str
    exception_type: str
    explanation: str
    evidence_digest: str
    related_source_keys: tuple[str, ...]
    available_actions: tuple[str, ...] = ("REVIEW_EVIDENCE", "KEEP_HELD")


@dataclass(frozen=True, slots=True)
class ReconciliationExceptionQueue:
    contract_version: str
    company_id: UUID
    items: tuple[ReconciliationExceptionItem, ...]
    queue_digest: str
    automatic_merge_enabled: bool = False


def exception_readback(
    evidence: tuple[HeldSourceException, ...],
    *,
    company_id: UUID,
    accessible_branch_ids: frozenset[UUID],
) -> ReconciliationExceptionQueue:
    items: list[ReconciliationExceptionItem] = []
    for row in sorted(
        evidence, key=lambda item: (item.source_key, item.evidence_digest)
    ):
        if row.company_id != company_id or row.branch_id not in accessible_branch_ids:
            continue
        identity = hashlib.sha256(
            f"{row.company_id}:{row.branch_id}:{row.source_key}:{row.evidence_digest}".encode()
        ).hexdigest()
        items.append(
            ReconciliationExceptionItem(
                identity,
                row.source_key,
                row.exception_type,
                row.explanation,
                row.evidence_digest,
                tuple(sorted(set(row.related_source_keys))),
            )
        )
    canonical = [
        {
            "id": item.exception_id,
            "source": item.source_key,
            "type": item.exception_type,
            "evidence": item.evidence_digest,
            "related": item.related_source_keys,
        }
        for item in items
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ReconciliationExceptionQueue(
        "twelvehats-reconciliation-exception-readback/v1",
        company_id,
        tuple(items),
        digest,
    )
