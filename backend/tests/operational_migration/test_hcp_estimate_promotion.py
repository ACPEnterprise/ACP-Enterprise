from __future__ import annotations

from dataclasses import replace

import pytest
from app.operational_migration.hcp_estimate_promotion import (
    EstimateLineEvidence,
    EstimateOptionEvidence,
    EstimatePromotionDisposition,
    EstimateSourceEvidence,
    ExactParentBindings,
    NativeEstimateEvidence,
    build_estimate_promotion_plan,
)

CUTOFF = "2026-09-12T23:59:59Z"
ACQUIRED = "2026-10-03T12:00:00Z"


def source(source_id: str = "estimate-1", digest: str = "1" * 64):
    line = EstimateLineEvidence("line-1", "Repair", "1", "100.00", "100.00")
    option = EstimateOptionEvidence("option-1", "Repair", "approved", "100.00", (line,))
    return EstimateSourceEvidence(
        source_id,
        "v2",
        digest,
        "2026-10-02T12:00:00Z",
        ACQUIRED,
        ACQUIRED,
        "customer-1",
        "location-1",
        "job-1",
        "open",
        "USD",
        "100.00",
        "0.00",
        "100.00",
        "Customer note",
        "employee-1",
        (option,),
    )


def bindings(*, jobs: tuple[str, ...] = ("native-job",)):
    return ExactParentBindings(
        ("native-customer",),
        ("native-location",),
        jobs,
        (("line-1", "commercial-snapshot-1"),),
    )


def plan(row, *, exact=None, native=None):
    return build_estimate_promotion_plan(
        cutoff=CUTOFF,
        acquired_at=ACQUIRED,
        source=(row,),
        bindings={row.source_id: exact or bindings()},
        native={row.source_id: native} if native else {},
    )


def test_create_preserves_open_state_lines_options_and_replays_stably() -> None:
    row = source()
    first = plan(row)
    second = plan(row)
    assert first == second
    assert first.decisions[0].disposition is EstimatePromotionDisposition.CREATE
    assert first.decisions[0].open_at_source is True
    assert len(first.decisions[0].snapshot_digest) == 64


def test_parent_linkage_fails_closed_without_blocking_history_only() -> None:
    row = source()
    ambiguous = plan(row, exact=bindings(jobs=("job-a", "job-b")))
    assert (
        ambiguous.decisions[0].disposition
        is EstimatePromotionDisposition.OWNER_DECISION_REQUIRED
    )
    missing_customer = plan(row, exact=ExactParentBindings((), (), ()))
    assert (
        missing_customer.decisions[0].disposition
        is EstimatePromotionDisposition.CONFLICT
    )
    history = plan(
        replace(row, job_source_id=None),
        exact=ExactParentBindings(("customer",), ("location",), ()),
    )
    assert history.decisions[0].disposition is EstimatePromotionDisposition.HISTORY_ONLY


def test_replay_update_and_native_newer_conflict_are_deterministic() -> None:
    row = source()
    replay_native = NativeEstimateEvidence(
        "native-1",
        row.source_digest,
        "v2",
        "2026-09-20T12:00:00Z",
        "2026-09-20T12:00:00Z",
    )
    assert (
        plan(row, native=replay_native).decisions[0].disposition
        is EstimatePromotionDisposition.REPLAY
    )
    prior = replace(replay_native, source_digest="2" * 64, source_version="v1")
    assert (
        plan(row, native=prior).decisions[0].disposition
        is EstimatePromotionDisposition.UPDATE
    )
    native_newer = replace(prior, native_updated_at="2026-10-02T18:00:00Z")
    assert (
        plan(row, native=native_newer).decisions[0].disposition
        is EstimatePromotionDisposition.CONFLICT
    )


def test_changed_same_version_and_unknown_status_fail_closed() -> None:
    row = source()
    same_version = NativeEstimateEvidence(
        "native-1", "2" * 64, "v2", "2026-09-20T12:00:00Z", "2026-09-20T12:00:00Z"
    )
    assert (
        plan(row, native=same_version).decisions[0].disposition
        is EstimatePromotionDisposition.CONFLICT
    )
    unknown = plan(replace(row, status="provider-mystery"))
    assert unknown.decisions[0].disposition is EstimatePromotionDisposition.UNSUPPORTED


def test_missing_commercial_snapshot_mapping_holds_open_and_preserves_closed_history() -> (
    None
):
    row = source()
    parents_only = ExactParentBindings(
        ("native-customer",), ("native-location",), ("native-job",)
    )
    open_result = plan(row, exact=parents_only)
    assert (
        open_result.decisions[0].disposition
        is EstimatePromotionDisposition.OWNER_DECISION_REQUIRED
    )
    closed_result = plan(replace(row, status="declined"), exact=parents_only)
    assert (
        closed_result.decisions[0].disposition
        is EstimatePromotionDisposition.HISTORY_ONLY
    )


def test_rejects_duplicate_line_identity_and_unknown_observations() -> None:
    row = source()
    option = row.options[0]
    duplicate = replace(row, options=(replace(option, lines=option.lines * 2),))
    with pytest.raises(ValueError, match="lines"):
        plan(duplicate)
    with pytest.raises(ValueError, match="unknown"):
        build_estimate_promotion_plan(
            cutoff=CUTOFF,
            acquired_at=ACQUIRED,
            source=(row,),
            bindings={row.source_id: bindings(), "other": bindings()},
            native={},
        )
