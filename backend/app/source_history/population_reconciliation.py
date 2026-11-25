"""Record-level historical population and relationship completeness readback."""

from __future__ import annotations

from dataclasses import dataclass

from .registration import SourceRegistration


@dataclass(frozen=True, slots=True)
class SourcePopulationRecord:
    source_key: str
    kind: str
    parent_source_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PopulationReconciliation:
    registration_id: str
    source_count: int
    unique_count: int
    complete_count: int
    held_count: int
    duplicate_source_keys: tuple[str, ...]
    missing_relationships: tuple[str, ...]
    kind_counts: tuple[tuple[str, int], ...]
    mutation_authority: str = "none"


def reconcile_population(
    registration: SourceRegistration,
    records: tuple[SourcePopulationRecord, ...],
) -> PopulationReconciliation:
    grouped: dict[str, list[SourcePopulationRecord]] = {}
    for record in records:
        if not record.source_key.strip() or not record.kind.strip():
            raise ValueError("source population identity is required")
        grouped.setdefault(record.source_key, []).append(record)
    known = set(grouped)
    duplicates = tuple(sorted(key for key, rows in grouped.items() if len(rows) > 1))
    missing: list[str] = []
    complete = 0
    kind_counts: dict[str, int] = {}
    for key in sorted(grouped):
        row = grouped[key][0]
        kind_counts[row.kind] = kind_counts.get(row.kind, 0) + 1
        unresolved = tuple(
            parent for parent in row.parent_source_keys if parent not in known
        )
        if len(grouped[key]) > 1:
            continue
        if unresolved:
            missing.extend(f"{key}->{parent}" for parent in unresolved)
            continue
        complete += 1
    held = len(grouped) - complete
    return PopulationReconciliation(
        registration.registration_id,
        len(records),
        len(grouped),
        complete,
        held,
        duplicates,
        tuple(sorted(missing)),
        tuple(sorted(kind_counts.items())),
    )
