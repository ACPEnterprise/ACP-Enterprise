"""Deterministic, fail-closed classification of legacy Preview projections.

Record evidence is private.  The public report contains only aggregate counts and a
canonical digest.  This classifier explains legacy rows; it does not relax the
canonical successor-reconciliation admission guard.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.operational_migration.hcp_successor_reconciliation import (
    LEGACY_SOURCE_SYSTEM,
    SOURCE4_SOURCE_SYSTEM,
    IdentityBinding,
    SealedIdentity,
)

CONTRACT = "hcp-legacy-projection-classification/v1"
SUPPORTED_DOMAINS = frozenset(
    {
        "customer",
        "contact",
        "service_location",
        "job",
        "appointment",
        "estimate",
        "invoice",
        "payment",
    }
)


class LegacyProjectionDisposition(StrEnum):
    SEALED_CREATE_NEW = "sealed_create_new"
    SEALED_REUSE_LEGACY = "sealed_reuse_legacy"
    SEALED_ALREADY_SUCCESSOR = "sealed_already_successor"
    LEGACY_OUTSIDE_SEALED = "legacy_outside_sealed"
    CONFLICT = "conflict"


@dataclass(frozen=True, order=True)
class LegacyProjectionRecord:
    domain: str
    source_id: str
    disposition: LegacyProjectionDisposition
    evidence_digest: str
    target_id: str | None = None
    canonical_blocker: bool = False


@dataclass(frozen=True)
class LegacyProjectionReport:
    contract: str
    disposition_counts: dict[str, int]
    domain_counts: dict[str, dict[str, int]]
    record_count: int
    canonical_blocker_count: int
    canonical_admission_allowed: bool
    safe_digest: str


@dataclass(frozen=True)
class LegacyProjectionClassification:
    """Private records plus an identifier-free public report."""

    records: tuple[LegacyProjectionRecord, ...]
    report: LegacyProjectionReport


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def classify_legacy_projections(
    *,
    current_bindings: Iterable[IdentityBinding],
    sealed_source4: Iterable[SealedIdentity],
) -> LegacyProjectionClassification:
    """Classify the complete sealed/Preview identity union without mutation."""

    bindings = tuple(current_bindings)
    sealed = tuple(sealed_source4)
    if any(
        item.domain not in SUPPORTED_DOMAINS or not item.source_id for item in sealed
    ):
        raise ValueError("sealed projection identity is invalid")
    sealed_keys = {(item.domain, item.source_id) for item in sealed}
    if len(sealed_keys) != len(sealed):
        raise ValueError("sealed projection identities contain duplicates")
    if any(
        item.domain not in SUPPORTED_DOMAINS
        or item.source_system not in {LEGACY_SOURCE_SYSTEM, SOURCE4_SOURCE_SYSTEM}
        or not item.source_id
        or not item.target_id
        for item in bindings
    ):
        raise ValueError("Preview projection binding is invalid")

    by_key: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    target_owners: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for item in bindings:
        by_key[(item.domain, item.source_id)][item.source_system].append(item.target_id)
        target_owners[(item.domain, item.source_system, item.target_id)].add(
            item.source_id
        )

    records: list[LegacyProjectionRecord] = []
    for domain, source_id in sorted(sealed_keys | set(by_key)):
        systems = by_key.get((domain, source_id), {})
        legacy = systems.get(LEGACY_SOURCE_SYSTEM, [])
        successor = systems.get(SOURCE4_SOURCE_SYSTEM, [])
        collision = any(
            len(target_owners[(domain, system, target)]) != 1
            for system, targets in (
                (LEGACY_SOURCE_SYSTEM, legacy),
                (SOURCE4_SOURCE_SYSTEM, successor),
            )
            for target in targets
        )
        sealed_key = (domain, source_id) in sealed_keys
        target: str | None = None
        blocker = False
        if len(legacy) > 1 or len(successor) > 1 or collision:
            disposition = LegacyProjectionDisposition.CONFLICT
            blocker = True
        elif not sealed_key:
            disposition = (
                LegacyProjectionDisposition.LEGACY_OUTSIDE_SEALED
                if legacy and not successor
                else LegacyProjectionDisposition.CONFLICT
            )
            target = (
                legacy[0]
                if disposition
                == LegacyProjectionDisposition.LEGACY_OUTSIDE_SEALED
                else None
            )
            blocker = True
        elif successor and legacy and successor[0] == legacy[0]:
            disposition = LegacyProjectionDisposition.SEALED_ALREADY_SUCCESSOR
            target = successor[0]
        elif successor:
            disposition = LegacyProjectionDisposition.CONFLICT
            blocker = True
        elif legacy:
            disposition = LegacyProjectionDisposition.SEALED_REUSE_LEGACY
            target = legacy[0]
        else:
            disposition = LegacyProjectionDisposition.SEALED_CREATE_NEW
        evidence = _digest(
            {
                "domain": domain,
                "source_id": source_id,
                "legacy_targets": sorted(legacy),
                "successor_targets": sorted(successor),
                "disposition": disposition.value,
            }
        )
        records.append(
            LegacyProjectionRecord(
                domain,
                source_id,
                disposition,
                evidence,
                target_id=target,
                canonical_blocker=blocker,
            )
        )

    disposition_counts = Counter(item.disposition.value for item in records)
    domain_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        domain_counts[record.domain][record.disposition.value] += 1
    keys = tuple(item.value for item in LegacyProjectionDisposition)
    public_counts = {key: disposition_counts[key] for key in keys}
    public_domains = {
        domain: {key: counts[key] for key in keys}
        for domain, counts in sorted(domain_counts.items())
    }
    blocker_count = sum(item.canonical_blocker for item in records)
    public = {
        "contract": CONTRACT,
        "disposition_counts": public_counts,
        "domain_counts": public_domains,
        "record_count": len(records),
        "canonical_blocker_count": blocker_count,
    }
    return LegacyProjectionClassification(
        records=tuple(records),
        report=LegacyProjectionReport(
            contract=CONTRACT,
            disposition_counts=public_counts,
            domain_counts=public_domains,
            record_count=len(records),
            canonical_blocker_count=blocker_count,
            canonical_admission_allowed=blocker_count == 0,
            safe_digest=_digest(public),
        ),
    )
