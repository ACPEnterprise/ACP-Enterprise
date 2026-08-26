from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType


class SnapshotRunState(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True)
class SourceObservation:
    entity_kind: str
    native_id: str
    envelope_sha256: str
    raw_sha256: str
    sync_token: str | None
    transaction_date: date | None

    @property
    def key(self) -> str:
        return f"{self.entity_kind}:{self.native_id}"


@dataclass(frozen=True)
class SnapshotInventory:
    snapshot_id: str
    manifest_sha256: str
    state: SnapshotRunState
    observations: Mapping[str, SourceObservation]
    page_digests: tuple[str, ...]
    deletion_detection_supported: bool = False

    def __post_init__(self) -> None:
        if not self.snapshot_id or not self.manifest_sha256:
            raise ValueError("sealed snapshot identity is required")
        copied = dict(self.observations)
        if any(key != observation.key for key, observation in copied.items()):
            raise ValueError("observation key mismatch")
        object.__setattr__(self, "observations", MappingProxyType(copied))


class DriftKind(str, Enum):
    CHANGED = "changed"
    CHANGED_EARLIER_DATED = "changed_earlier_dated"
    NEW = "new"
    DELETED = "deleted"
    UNAVAILABLE = "unavailable"
    PAGINATION_CHANGED = "pagination_changed"
    PARTIAL_COMPARISON = "partial_comparison"


@dataclass(frozen=True)
class DriftFinding:
    kind: DriftKind
    entity_key: str | None
    snapshot_a_id: str
    snapshot_b_id: str
    observation_a: SourceObservation | None
    observation_b: SourceObservation | None


def compare_snapshots(
    snapshot_a: SnapshotInventory,
    snapshot_b: SnapshotInventory,
    *,
    cutoff: date,
) -> tuple[DriftFinding, ...]:
    findings: list[DriftFinding] = []
    if SnapshotRunState.PARTIAL in {snapshot_a.state, snapshot_b.state}:
        findings.append(
            DriftFinding(
                kind=DriftKind.PARTIAL_COMPARISON,
                entity_key=None,
                snapshot_a_id=snapshot_a.snapshot_id,
                snapshot_b_id=snapshot_b.snapshot_id,
                observation_a=None,
                observation_b=None,
            )
        )
    keys = sorted(set(snapshot_a.observations) | set(snapshot_b.observations))
    for key in keys:
        before = snapshot_a.observations.get(key)
        after = snapshot_b.observations.get(key)
        if before is None:
            kind = DriftKind.NEW
        elif after is None:
            kind = (
                DriftKind.DELETED
                if snapshot_b.deletion_detection_supported
                else DriftKind.UNAVAILABLE
            )
        elif (before.raw_sha256, before.sync_token) != (
            after.raw_sha256,
            after.sync_token,
        ):
            kind = (
                DriftKind.CHANGED_EARLIER_DATED
                if after.transaction_date is not None
                and after.transaction_date <= cutoff
                else DriftKind.CHANGED
            )
        else:
            continue
        findings.append(
            DriftFinding(
                kind=kind,
                entity_key=key,
                snapshot_a_id=snapshot_a.snapshot_id,
                snapshot_b_id=snapshot_b.snapshot_id,
                observation_a=before,
                observation_b=after,
            )
        )
    if snapshot_a.page_digests != snapshot_b.page_digests:
        findings.append(
            DriftFinding(
                kind=DriftKind.PAGINATION_CHANGED,
                entity_key=None,
                snapshot_a_id=snapshot_a.snapshot_id,
                snapshot_b_id=snapshot_b.snapshot_id,
                observation_a=None,
                observation_b=None,
            )
        )
    return tuple(findings)
