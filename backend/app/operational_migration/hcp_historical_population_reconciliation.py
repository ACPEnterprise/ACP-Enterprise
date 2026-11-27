"""Non-destructive reconciliation of two HCP historical population snapshots."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass

DOMAINS = ("customer", "location", "job", "appointment")
EXCLUDED_DISPOSITIONS = frozenset({"EXCLUDED", "HELD", "QUARANTINED"})


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    domain: str
    source_id: str
    target_id: str | None
    parent_source_keys: tuple[str, ...]
    source_digest: str
    admission_disposition: str
    merged_into_source_id: str | None = None


@dataclass(frozen=True, slots=True)
class PopulationSnapshot:
    snapshot_id: str
    acquired_at: str
    provenance_digest: str
    records: tuple[SnapshotRecord, ...]


@dataclass(frozen=True, slots=True)
class HistoricalPopulationReconciliation:
    previous_snapshot_id: str
    current_snapshot_id: str
    previous_counts: dict[str, int]
    current_counts: dict[str, int]
    missing_identities: tuple[str, ...]
    added_identities: tuple[str, ...]
    duplicate_customer_targets: tuple[tuple[str, tuple[str, ...]], ...]
    merged_customers: tuple[tuple[str, str], ...]
    missing_locations: tuple[str, ...]
    orphaned_jobs: tuple[str, ...]
    orphaned_appointments: tuple[str, ...]
    target_identity_mismatches: tuple[str, ...]
    excluded_records: tuple[str, ...]
    provenance_differences: tuple[str, ...]
    digest: str
    mutation_authority: str = "none"


def _validate(snapshot: PopulationSnapshot) -> None:
    if not snapshot.snapshot_id or not snapshot.acquired_at:
        raise ValueError("snapshot identity and acquisition time are required")
    if len(snapshot.provenance_digest) != 64:
        raise ValueError("snapshot provenance digest is invalid")
    for row in snapshot.records:
        if row.domain not in DOMAINS or not row.source_id:
            raise ValueError("snapshot record identity is invalid")
        if len(row.source_digest) != 64:
            raise ValueError("snapshot record digest is invalid")


def _index(
    snapshot: PopulationSnapshot,
) -> tuple[dict[str, SnapshotRecord], tuple[str, ...]]:
    grouped: dict[str, list[SnapshotRecord]] = defaultdict(list)
    for row in snapshot.records:
        grouped[f"{row.domain}:{row.source_id}"].append(row)
    duplicates = tuple(sorted(key for key, rows in grouped.items() if len(rows) > 1))
    return {key: rows[0] for key, rows in grouped.items()}, duplicates


def reconcile_historical_population(
    previous: PopulationSnapshot, current: PopulationSnapshot
) -> HistoricalPopulationReconciliation:
    _validate(previous)
    _validate(current)
    previous_index, previous_duplicates = _index(previous)
    current_index, current_duplicates = _index(current)

    previous_keys = set(previous_index)
    current_keys = set(current_index)
    missing = tuple(sorted(previous_keys - current_keys))
    added = tuple(sorted(current_keys - previous_keys))

    customer_targets: dict[str, set[str]] = defaultdict(set)
    merged: list[tuple[str, str]] = []
    for row in current.records:
        if row.domain != "customer":
            continue
        if row.target_id:
            customer_targets[row.target_id].add(row.source_id)
        if row.merged_into_source_id:
            merged.append((row.source_id, row.merged_into_source_id))
    duplicate_targets = tuple(
        sorted(
            (target, tuple(sorted(source_ids)))
            for target, source_ids in customer_targets.items()
            if len(source_ids) > 1
        )
    )

    target_mismatches = tuple(
        sorted(
            key
            for key in previous_keys & current_keys
            if previous_index[key].target_id != current_index[key].target_id
        )
    )
    referenced_missing_locations = {
        parent
        for row in current.records
        for parent in row.parent_source_keys
        if parent.startswith("location:") and parent not in current_keys
    }
    missing_locations = tuple(
        sorted(
            {key for key in missing if key.startswith("location:")}
            | referenced_missing_locations
        )
    )
    current_customers = {key for key in current_keys if key.startswith("customer:")}
    current_locations = {key for key in current_keys if key.startswith("location:")}
    current_jobs = {key for key in current_keys if key.startswith("job:")}
    orphaned_jobs = tuple(
        sorted(
            f"job:{row.source_id}"
            for row in current.records
            if row.domain == "job"
            and any(
                (parent.startswith("location:") and parent not in current_locations)
                or (parent.startswith("customer:") and parent not in current_customers)
                for parent in row.parent_source_keys
            )
        )
    )
    orphaned_appointments = tuple(
        sorted(
            f"appointment:{row.source_id}"
            for row in current.records
            if row.domain == "appointment"
            and any(
                parent.startswith("job:") and parent not in current_jobs
                for parent in row.parent_source_keys
            )
        )
    )
    excluded = tuple(
        sorted(
            f"{row.domain}:{row.source_id}"
            for row in current.records
            if row.admission_disposition in EXCLUDED_DISPOSITIONS
        )
    )
    provenance = []
    if previous.provenance_digest != current.provenance_digest:
        provenance.append("provenance_digest_changed")
    if previous.acquired_at != current.acquired_at:
        provenance.append("acquired_at_changed")
    provenance.extend(f"previous_duplicate:{key}" for key in previous_duplicates)
    provenance.extend(f"current_duplicate:{key}" for key in current_duplicates)

    previous_counts = dict(Counter(row.domain for row in previous.records))
    current_counts = dict(Counter(row.domain for row in current.records))
    evidence = {
        "previous_snapshot_id": previous.snapshot_id,
        "current_snapshot_id": current.snapshot_id,
        "previous_counts": previous_counts,
        "current_counts": current_counts,
        "missing_identities": missing,
        "added_identities": added,
        "duplicate_customer_targets": duplicate_targets,
        "merged_customers": sorted(merged),
        "missing_locations": missing_locations,
        "orphaned_jobs": orphaned_jobs,
        "orphaned_appointments": orphaned_appointments,
        "target_identity_mismatches": target_mismatches,
        "excluded_records": excluded,
        "provenance_differences": provenance,
    }
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return HistoricalPopulationReconciliation(
        previous.snapshot_id,
        current.snapshot_id,
        previous_counts,
        current_counts,
        missing,
        added,
        duplicate_targets,
        tuple(sorted(merged)),
        missing_locations,
        orphaned_jobs,
        orphaned_appointments,
        target_mismatches,
        excluded,
        tuple(provenance),
        digest,
    )
