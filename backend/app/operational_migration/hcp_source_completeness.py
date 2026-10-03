"""Account for every identity in a sealed HCP cutover observation.

This module is deliberately read-only.  It describes whether an identity is a
safe create/update/replay or a quarantined conflict; execution remains owned by
the canonical operational migration services.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from app.operational_migration.hcp_continuous_delta import (
    ContinuousDeltaPlan,
    DeltaDisposition,
)

CONTRACT: Final = "hcp-cutover-source-completeness/v1"
REQUIRED_DOMAINS: Final = (
    "customer",
    "job",
    "estimate",
    "appointment",
    "invoice",
    "payment",
    "employee_identity",
    "open_work_reference",
)


class CompletenessDisposition(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    CONFLICT = "CONFLICT"
    REPLAY = "REPLAY"


@dataclass(frozen=True)
class SourceIdentity:
    domain: str
    source_id: str
    source_version: str | None
    source_digest: str


@dataclass(frozen=True)
class CompletenessRecord:
    source: SourceIdentity
    disposition: CompletenessDisposition
    reason: str


@dataclass(frozen=True)
class DomainCompleteness:
    domain: str
    source: int
    create: int
    update: int
    conflict: int
    replay: int
    unexplained: int
    source_versions: tuple[str, ...]


@dataclass(frozen=True)
class SourceCompletenessManifest:
    contract: str
    cutoff: str
    acquired_at: str
    records: tuple[CompletenessRecord, ...]
    domains: tuple[DomainCompleteness, ...]
    unexplained_provider_gaps: int
    digest: str


def build_source_completeness(
    *,
    cutoff: str,
    acquired_at: str,
    source: tuple[SourceIdentity, ...],
    delta: ContinuousDeltaPlan,
) -> SourceCompletenessManifest:
    """Bind the sealed source inventory to one explicit disposition per ID."""
    source_keys = [(row.domain, row.source_id) for row in source]
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("sealed provider identities must be unique")
    decisions = {
        (row.key.domain, row.key.source_id): row for row in delta.decisions
    }
    extra = set(decisions) - set(source_keys)
    if extra:
        raise ValueError("delta contains identities absent from sealed source inventory")

    records: list[CompletenessRecord] = []
    unexplained_by_domain: Counter[str] = Counter()
    for row in sorted(source, key=lambda value: (value.domain, value.source_id)):
        _digest(row.source_digest)
        decision = decisions.get((row.domain, row.source_id))
        if decision is None:
            unexplained_by_domain[row.domain] += 1
            continue
        disposition = {
            DeltaDisposition.CREATE: CompletenessDisposition.CREATE,
            DeltaDisposition.UPDATE: CompletenessDisposition.UPDATE,
            DeltaDisposition.UNCHANGED_REPLAY: CompletenessDisposition.REPLAY,
        }.get(decision.disposition, CompletenessDisposition.CONFLICT)
        records.append(CompletenessRecord(row, disposition, decision.reason))

    grouped: dict[str, list[CompletenessRecord]] = defaultdict(list)
    source_counts: Counter[str] = Counter(row.domain for row in source)
    versions: dict[str, set[str]] = defaultdict(set)
    for source_row in source:
        if source_row.source_version:
            versions[source_row.domain].add(source_row.source_version)
    for record in records:
        grouped[record.source.domain].append(record)
    domains = tuple(
        _domain(
            domain,
            source_counts[domain],
            grouped[domain],
            unexplained_by_domain[domain],
            versions[domain],
        )
        for domain in sorted(set(REQUIRED_DOMAINS) | set(source_counts))
    )
    unexplained = sum(row.unexplained for row in domains)
    payload = {
        "contract": CONTRACT,
        "cutoff": cutoff,
        "acquired_at": acquired_at,
        "records": [_record_value(row) for row in records],
        "domains": [_domain_value(row) for row in domains],
        "unexplained_provider_gaps": unexplained,
    }
    return SourceCompletenessManifest(
        CONTRACT,
        cutoff,
        acquired_at,
        tuple(records),
        domains,
        unexplained,
        hashlib.sha256(_canonical(payload)).hexdigest(),
    )


def _domain(
    domain: str,
    source: int,
    rows: list[CompletenessRecord],
    unexplained: int,
    versions: set[str],
) -> DomainCompleteness:
    counts = Counter(row.disposition for row in rows)
    accounted = sum(counts.values()) + unexplained
    if accounted != source:
        raise ValueError(f"{domain} source accounting mismatch")
    return DomainCompleteness(
        domain,
        source,
        counts[CompletenessDisposition.CREATE],
        counts[CompletenessDisposition.UPDATE],
        counts[CompletenessDisposition.CONFLICT],
        counts[CompletenessDisposition.REPLAY],
        unexplained,
        tuple(sorted(versions)),
    )


def _record_value(row: CompletenessRecord) -> dict[str, Any]:
    return {
        "domain": row.source.domain,
        "source_id": row.source.source_id,
        "source_version": row.source.source_version,
        "source_digest": row.source.source_digest,
        "disposition": row.disposition.value,
        "reason": row.reason,
    }


def _domain_value(row: DomainCompleteness) -> dict[str, Any]:
    return {
        "domain": row.domain,
        "source": row.source,
        "create": row.create,
        "update": row.update,
        "conflict": row.conflict,
        "replay": row.replay,
        "unexplained": row.unexplained,
        "source_versions": list(row.source_versions),
    }


def manifest_value(value: SourceCompletenessManifest) -> dict[str, Any]:
    return {
        "contract": value.contract,
        "cutoff": value.cutoff,
        "acquired_at": value.acquired_at,
        "records": [_record_value(row) for row in value.records],
        "domains": [_domain_value(row) for row in value.domains],
        "unexplained_provider_gaps": value.unexplained_provider_gaps,
        "digest": value.digest,
    }


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: str) -> None:
    if len(value) != 64:
        raise ValueError("source digest is invalid")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError("source digest is invalid") from error
