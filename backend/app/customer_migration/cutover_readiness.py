"""Immutable, read-only cutover-readiness contracts for Customer Migration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

CUTOVER_READINESS_VERSION = "customer-migration-cutover-readiness/v1"


class PrerequisiteStatus(StrEnum):
    COMPLETE = "complete"
    MISSING = "missing"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CutoverPrerequisite:
    code: str
    status: PrerequisiteStatus
    required: bool
    evidence_digest: str | None

    def __post_init__(self) -> None:
        if not self.code or self.code.strip() != self.code:
            raise ValueError("prerequisite code must be normalized")
        if self.status is PrerequisiteStatus.COMPLETE and not _is_sha256(
            self.evidence_digest
        ):
            raise ValueError("completed prerequisite requires immutable evidence")


@dataclass(frozen=True)
class ReadinessCategoryCount:
    category: str
    count: int

    def __post_init__(self) -> None:
        if (
            not self.category
            or self.category.strip() != self.category
            or self.count < 0
        ):
            raise ValueError("readiness category count is invalid")


@dataclass(frozen=True)
class CutoverEvidenceSnapshot:
    company_id: UUID
    branch_id: UUID
    prerequisites: tuple[CutoverPrerequisite, ...]
    owner_dispositions: tuple[ReadinessCategoryCount, ...]
    reconciliation_items: tuple[ReadinessCategoryCount, ...]
    source_evidence_digests: tuple[str, ...]
    total_evidence_items: int
    deterministically_resolved_items: int

    def __post_init__(self) -> None:
        if (
            self.total_evidence_items < 0
            or not 0
            <= self.deterministically_resolved_items
            <= self.total_evidence_items
        ):
            raise ValueError("readiness evidence totals do not reconcile")
        if len({item.code for item in self.prerequisites}) != len(self.prerequisites):
            raise ValueError("prerequisite codes must be unique")
        if any(not _is_sha256(value) for value in self.source_evidence_digests):
            raise ValueError("source evidence digest is invalid")
        for values in (self.owner_dispositions, self.reconciliation_items):
            if len({item.category for item in values}) != len(values):
                raise ValueError("readiness categories must be unique")


@dataclass(frozen=True)
class CutoverReadiness:
    readiness_id: UUID
    readiness_key: str
    ready: bool
    status: str
    completed_prerequisites: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    blocking_conditions: tuple[str, ...]
    unresolved_owner_dispositions: tuple[ReadinessCategoryCount, ...]
    unresolved_reconciliation_items: tuple[ReadinessCategoryCount, ...]
    confidence_basis_points: int
    completeness_basis_points: int
    evidence_digest: str


def _is_sha256(value: str | None) -> bool:
    return (
        value is not None
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def assess_cutover_readiness(snapshot: CutoverEvidenceSnapshot) -> CutoverReadiness:
    """Assess existing evidence only; this function cannot import or mutate entities."""
    prerequisites = tuple(sorted(snapshot.prerequisites, key=lambda item: item.code))
    owner = tuple(sorted(snapshot.owner_dispositions, key=lambda item: item.category))
    reconciliation = tuple(
        sorted(snapshot.reconciliation_items, key=lambda item: item.category)
    )
    completed = tuple(
        item.code
        for item in prerequisites
        if item.status is PrerequisiteStatus.COMPLETE
    )
    missing = tuple(
        item.code
        for item in prerequisites
        if item.required and item.status is not PrerequisiteStatus.COMPLETE
    )
    blockers: set[str] = set()
    blockers.update(
        f"prerequisite:{item.code}:{item.status.value}"
        for item in prerequisites
        if item.required and item.status is not PrerequisiteStatus.COMPLETE
    )
    blockers.update(
        f"owner_disposition:{item.category}" for item in owner if item.count
    )
    blockers.update(
        f"reconciliation:{item.category}" for item in reconciliation if item.count
    )
    if snapshot.deterministically_resolved_items != snapshot.total_evidence_items:
        blockers.add("evidence:incomplete_resolution")
    if not snapshot.source_evidence_digests:
        blockers.add("evidence:missing_source_digests")
    required_count = sum(item.required for item in prerequisites)
    completed_required = sum(
        item.required and item.status is PrerequisiteStatus.COMPLETE
        for item in prerequisites
    )
    completeness = (
        10000 if required_count == 0 else completed_required * 10000 // required_count
    )
    confidence = (
        10000
        if snapshot.total_evidence_items == 0 and snapshot.source_evidence_digests
        else (
            snapshot.deterministically_resolved_items
            * 10000
            // snapshot.total_evidence_items
            if snapshot.total_evidence_items
            else 0
        )
    )
    canonical = [
        CUTOVER_READINESS_VERSION,
        snapshot.company_id,
        snapshot.branch_id,
        prerequisites,
        owner,
        reconciliation,
        tuple(sorted(snapshot.source_evidence_digests)),
        snapshot.total_evidence_items,
        snapshot.deterministically_resolved_items,
        tuple(sorted(blockers)),
        completeness,
        confidence,
    ]
    evidence_digest = _digest(canonical)
    readiness_key = _digest(
        [
            CUTOVER_READINESS_VERSION,
            snapshot.company_id,
            snapshot.branch_id,
            evidence_digest,
        ]
    )
    ready = not blockers
    return CutoverReadiness(
        readiness_id=UUID(readiness_key[:32]),
        readiness_key=readiness_key,
        ready=ready,
        status="ready_for_owner_review" if ready else "not_ready",
        completed_prerequisites=completed,
        missing_prerequisites=missing,
        blocking_conditions=tuple(sorted(blockers)),
        unresolved_owner_dispositions=tuple(item for item in owner if item.count),
        unresolved_reconciliation_items=tuple(
            item for item in reconciliation if item.count
        ),
        confidence_basis_points=confidence,
        completeness_basis_points=completeness,
        evidence_digest=evidence_digest,
    )
