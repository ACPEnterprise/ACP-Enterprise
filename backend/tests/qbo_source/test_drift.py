from __future__ import annotations

from datetime import date

from app.qbo_source.drift import (
    DriftKind,
    SnapshotInventory,
    SnapshotRunState,
    SourceObservation,
    compare_snapshots,
)


def observation(
    native_id: str,
    *,
    raw: str,
    token: str,
    transaction_date: date | None = date(2026, 8, 20),
) -> SourceObservation:
    return SourceObservation(
        entity_kind="invoice",
        native_id=native_id,
        envelope_sha256=(raw[0] if raw else "e") * 64,
        raw_sha256=raw * 64,
        sync_token=token,
        transaction_date=transaction_date,
    )


def test_repeat_snapshot_retains_changed_old_new_and_unavailable_observations() -> None:
    old_changed = observation("changed", raw="a", token="1")
    new_changed = observation("changed", raw="b", token="2")
    old_missing = observation("missing", raw="c", token="1")
    new_record = observation(
        "new", raw="d", token="0", transaction_date=date(2026, 8, 26)
    )
    snapshot_a = SnapshotInventory(
        "snapshot-a",
        "1" * 64,
        SnapshotRunState.COMPLETE,
        {old_changed.key: old_changed, old_missing.key: old_missing},
        ("page-a",),
    )
    snapshot_b = SnapshotInventory(
        "snapshot-b",
        "2" * 64,
        SnapshotRunState.COMPLETE,
        {new_changed.key: new_changed, new_record.key: new_record},
        ("page-b", "page-b2"),
        deletion_detection_supported=False,
    )

    findings = compare_snapshots(snapshot_a, snapshot_b, cutoff=date(2026, 8, 25))

    assert [finding.kind for finding in findings] == [
        DriftKind.CHANGED_EARLIER_DATED,
        DriftKind.UNAVAILABLE,
        DriftKind.NEW,
        DriftKind.PAGINATION_CHANGED,
    ]
    changed = findings[0]
    assert changed.observation_a == old_changed
    assert changed.observation_b == new_changed
    assert snapshot_a.observations[old_changed.key].sync_token == "1"


def test_detectable_delete_and_partial_comparison_are_explicit() -> None:
    deleted = observation("deleted", raw="e", token="3")
    snapshot_a = SnapshotInventory(
        "snapshot-a",
        "a" * 64,
        SnapshotRunState.COMPLETE,
        {deleted.key: deleted},
        (),
    )
    snapshot_b = SnapshotInventory(
        "snapshot-b",
        "b" * 64,
        SnapshotRunState.PARTIAL,
        {},
        (),
        deletion_detection_supported=True,
    )

    findings = compare_snapshots(snapshot_a, snapshot_b, cutoff=date(2026, 8, 25))

    assert [finding.kind for finding in findings] == [
        DriftKind.PARTIAL_COMPARISON,
        DriftKind.DELETED,
    ]
