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
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum

from app.operational_migration.hcp_successor_reconciliation import (
    LEGACY_SOURCE_SYSTEM,
    SOURCE4_SOURCE_SYSTEM,
    IdentityBinding,
    SealedIdentity,
)

CONTRACT = "hcp-legacy-projection-classification/v2"
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
    PROVABLY_UNRELATED = "provably_unrelated"
    EXACT_SUCCESSOR = "exact_successor"
    AMBIGUOUS_HOLD = "ambiguous_hold"
    GENUINE_CONFLICT = "genuine_conflict"
    SEALED_CREATE_NEW = "sealed_create_new"


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


@dataclass(frozen=True)
class ProjectionCorrelationEvidence:
    """Private normalized evidence for one legacy or sealed projection.

    Fingerprints must represent independently acquired, domain-specific content.
    Parent keys are canonical source keys produced by an already qualified parent
    correlation.  Callers retain all raw values inside the protected boundary.
    """

    domain: str
    source_id: str
    target_id: str | None
    content_fingerprints: tuple[str, ...] = ()
    parent_keys: tuple[tuple[str, str], ...] = ()
    authoritative_provider_id: str | None = None


def classify_correlated_legacy(
    *,
    legacy: Iterable[ProjectionCorrelationEvidence],
    sealed: Iterable[ProjectionCorrelationEvidence],
) -> LegacyProjectionClassification:
    """Classify legacy projections from provider, content, and graph evidence.

    A reuse is exact only when every available unique signal agrees on one sealed
    projection. Conflicting unique signals are genuine conflicts. Evidence with no
    positive correlation is held unless an authoritative provider identifier proves
    the records distinct; negative fuzzy matching is deliberately never sufficient.
    """

    old = tuple(legacy)
    new = tuple(sealed)
    all_rows = old + new
    if any(
        row.domain not in SUPPORTED_DOMAINS
        or not row.source_id
        or any(len(value) != 64 for value in row.content_fingerprints)
        for row in all_rows
    ):
        raise ValueError("projection correlation evidence is invalid")
    keys = [(row.domain, row.source_id) for row in new]
    if len(keys) != len(set(keys)):
        raise ValueError("sealed projection evidence contains duplicates")

    provider: dict[tuple[str, str], set[str]] = defaultdict(set)
    fingerprints: dict[tuple[str, str], set[str]] = defaultdict(set)
    parents: dict[tuple[str, tuple[tuple[str, str], ...]], set[str]] = defaultdict(set)
    sealed_by_key = {(row.domain, row.source_id): row for row in new}
    for row in new:
        if row.authoritative_provider_id:
            provider[(row.domain, row.authoritative_provider_id)].add(row.source_id)
        for value in row.content_fingerprints:
            fingerprints[(row.domain, value)].add(row.source_id)
        if row.parent_keys:
            parents[(row.domain, row.parent_keys)].add(row.source_id)

    records: list[LegacyProjectionRecord] = []
    for row in sorted(old, key=lambda item: (item.domain, item.source_id)):
        signals: list[set[str]] = []
        if row.authoritative_provider_id:
            signals.append(provider[(row.domain, row.authoritative_provider_id)])
        signals.extend(
            fingerprints[(row.domain, value)] for value in row.content_fingerprints
        )
        # Graph evidence constrains a positive content/provider signal; a unique
        # child beneath a parent is not, by itself, proof that two events are equal.
        if row.parent_keys and signals:
            parent_candidates = parents[(row.domain, row.parent_keys)]
            signals = [value & parent_candidates for value in signals]
        unique = {next(iter(value)) for value in signals if len(value) == 1}
        if len(unique) > 1:
            disposition = LegacyProjectionDisposition.GENUINE_CONFLICT
            successor_id = None
            blocker = True
        elif len(unique) == 1:
            successor_id = next(iter(unique))
            disposition = LegacyProjectionDisposition.EXACT_SUCCESSOR
            blocker = False
        elif row.authoritative_provider_id and not provider[
            (row.domain, row.authoritative_provider_id)
        ]:
            successor_id = None
            disposition = LegacyProjectionDisposition.PROVABLY_UNRELATED
            blocker = False
        else:
            successor_id = None
            disposition = LegacyProjectionDisposition.AMBIGUOUS_HOLD
            blocker = True
        records.append(
            LegacyProjectionRecord(
                domain=row.domain,
                source_id=row.source_id,
                disposition=disposition,
                evidence_digest=_digest(
                    {
                        "legacy": row,
                        "successor": sealed_by_key.get((row.domain, successor_id)),
                        "disposition": disposition.value,
                    }
                ),
                target_id=row.target_id,
                canonical_blocker=blocker,
            )
        )
    return _classification(tuple(records))


def _digest(value: object) -> str:
    def normalize(item: object) -> object:
        if is_dataclass(item):
            return normalize(asdict(item))
        if isinstance(item, dict):
            return {str(key): normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if isinstance(item, StrEnum):
            return item.value
        return item

    return hashlib.sha256(
        json.dumps(normalize(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _classification(
    records: tuple[LegacyProjectionRecord, ...],
) -> LegacyProjectionClassification:
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
        records=records,
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
            disposition = LegacyProjectionDisposition.GENUINE_CONFLICT
            blocker = True
        elif not sealed_key:
            # Absence from the new provider-ID namespace is not proof that an old
            # projection is unrelated.  Fingerprint/graph evidence must promote it
            # to EXACT_SUCCESSOR or PROVABLY_UNRELATED; identity-only evidence holds.
            disposition = LegacyProjectionDisposition.AMBIGUOUS_HOLD
            target = legacy[0] if legacy and not successor else None
            blocker = True
        elif successor and legacy and successor[0] == legacy[0]:
            disposition = LegacyProjectionDisposition.EXACT_SUCCESSOR
            target = successor[0]
        elif successor:
            disposition = LegacyProjectionDisposition.GENUINE_CONFLICT
            blocker = True
        elif legacy:
            disposition = LegacyProjectionDisposition.EXACT_SUCCESSOR
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

    return _classification(tuple(records))
