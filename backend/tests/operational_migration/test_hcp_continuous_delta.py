from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from app.operational_migration.hcp_continuous_delta import (
    DeltaDisposition,
    NativeObservation,
    ProviderObservation,
    build_continuous_delta,
)
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayExecutor,
    OverlayAssertion,
    OverlayExecutionReceipt,
    OverlayKey,
    OverlayRecord,
    OverlaySourceState,
)

CUTOFF = "2026-09-12T23:59:59Z"
ACQUIRED = "2026-09-30T12:00:00Z"


def provider(
    source_id: str,
    digest: str,
    *,
    domain: str = "job",
    updated_at: str | None = "2026-09-29T12:00:00Z",
    parents: tuple[OverlayKey, ...] = (),
) -> ProviderObservation:
    return ProviderObservation(
        domain=domain,
        source_id=source_id,
        source_digest=digest,
        acquired_at=ACQUIRED,
        source_updated_at=updated_at,
        payload={"id": source_id, "updated_at": updated_at, "status": "scheduled"},
        parent_keys=parents,
        native_fingerprint=digest,
    )


def native(
    digest: str,
    *,
    applied: str = "2026-09-20T12:00:00Z",
    updated: str = "2026-09-20T12:00:00Z",
) -> NativeObservation:
    return NativeObservation(digest, applied, updated)


def build(
    *records: ProviderObservation,
    states: dict[OverlayKey, NativeObservation] | None = None,
):
    return build_continuous_delta(
        cutoff=CUTOFF,
        base_source4_digest="a" * 64,
        company_id="company",
        branch_id="branch",
        acquired_at=ACQUIRED,
        provider=records,
        native=states or {},
    )


def test_classifies_new_update_replay_and_native_newer_without_global_block() -> None:
    unchanged = provider("unchanged", "1" * 64)
    changed = provider("changed", "2" * 64)
    native_newer = provider("native-newer", "3" * 64)
    created = provider("new", "4" * 64)
    result = build(
        unchanged,
        changed,
        native_newer,
        created,
        states={
            unchanged.key: native("1" * 64),
            changed.key: native("5" * 64),
            native_newer.key: native(
                "6" * 64, updated="2026-09-28T12:00:00Z"
            ),
        },
    )

    assert [item.disposition for item in result.decisions] == [
        DeltaDisposition.UPDATE,
        DeltaDisposition.HOLD_NATIVE_NEWER,
        DeltaDisposition.CREATE,
        DeltaDisposition.UNCHANGED_REPLAY,
    ]
    assert result.manifest is not None
    assert [item.assertion for item in result.manifest.records] == [
        OverlayAssertion.UPDATE,
        OverlayAssertion.HOLD,
        OverlayAssertion.CREATE,
    ]


def test_changed_location_and_evidence_only_domains_fail_closed() -> None:
    location = provider("location", "1" * 64, domain="service_location")
    estimate = provider("estimate", "2" * 64, domain="estimate")
    result = build(
        location,
        estimate,
        states={
            location.key: native("3" * 64),
            estimate.key: native("4" * 64),
        },
    )
    assert {item.disposition for item in result.decisions} == {
        DeltaDisposition.HOLD_UNSUPPORTED_MUTATION
    }
    assert result.manifest is not None
    assert all(
        item.assertion is OverlayAssertion.HOLD for item in result.manifest.records
    )


def test_missing_or_non_successor_provider_chronology_is_held() -> None:
    missing = provider("missing-time", "1" * 64, updated_at=None)
    stale = provider(
        "stale", "2" * 64, updated_at="2026-09-19T12:00:00Z"
    )
    result = build(
        missing,
        stale,
        states={missing.key: native("3" * 64), stale.key: native("4" * 64)},
    )
    assert all(
        item.disposition is DeltaDisposition.HOLD_SOURCE_CHRONOLOGY
        for item in result.decisions
    )


def test_exact_replay_is_stable_and_produces_no_mutating_manifest() -> None:
    row = provider("same", "1" * 64)
    first = build(row, states={row.key: native("1" * 64)})
    second = build(row, states={row.key: native("1" * 64)})
    assert first == second
    assert first.manifest is None
    assert first.decisions[0].disposition is DeltaDisposition.UNCHANGED_REPLAY


def test_parent_identity_is_preserved_for_recent_appointment() -> None:
    parent = OverlayKey("job", "job-new")
    appointment = provider(
        "appointment-new",
        "1" * 64,
        domain="appointment",
        parents=(parent,),
    )
    result = build(appointment)
    assert result.manifest is not None
    assert result.manifest.records[0].parent_keys == (parent,)


class RehearsalRepository:
    def __init__(self) -> None:
        self.states: dict[OverlayKey, OverlaySourceState] = {}
        self.receipts: dict[str, OverlayExecutionReceipt] = {}
        self.holds: list[OverlayRecord] = []

    @asynccontextmanager
    async def transaction(self):  # type: ignore[no-untyped-def]
        yield

    async def prior_receipt(self, digest: str):  # type: ignore[no-untyped-def]
        return self.receipts.get(digest)

    async def source_state(self, key: OverlayKey):  # type: ignore[no-untyped-def]
        return self.states.get(key)

    async def source_exists(self, key: OverlayKey) -> bool:
        return key in self.states

    async def fingerprint_owners(self, domain: str, fingerprint: str):  # type: ignore[no-untyped-def]
        return ()

    async def create(self, record: OverlayRecord) -> OverlaySourceState:
        state = OverlaySourceState(
            record.source_digest, f"native-{record.source_id}", record.payload
        )
        self.states[record.key] = state
        return state

    async def update(
        self, state: OverlaySourceState, record: OverlayRecord
    ) -> OverlaySourceState:
        state = OverlaySourceState(record.source_digest, state.native_id, record.payload)
        self.states[record.key] = state
        return state

    async def record_non_mutating_assertion(self, record: OverlayRecord) -> None:
        self.holds.append(record)

    async def persist_receipt(self, receipt: OverlayExecutionReceipt) -> None:
        self.receipts[receipt.manifest_digest] = receipt


@pytest.mark.asyncio
async def test_rehearsal_applies_safe_majority_holds_conflict_and_replays() -> None:
    changed = provider("changed", "2" * 64)
    conflict = provider("conflict", "3" * 64)
    created = provider("created", "4" * 64)
    plan = build(
        changed,
        conflict,
        created,
        states={
            changed.key: native("5" * 64),
            conflict.key: native(
                "6" * 64, updated="2026-09-28T12:00:00Z"
            ),
        },
    )
    assert plan.manifest is not None
    repository = RehearsalRepository()
    repository.states[changed.key] = OverlaySourceState(
        "5" * 64, "native-changed", {}
    )
    repository.states[conflict.key] = OverlaySourceState(
        "6" * 64, "native-conflict", {}
    )
    executor = CurrentOverlayExecutor()
    first = await executor.execute(
        repository,
        manifest=plan.manifest,
        expected_base_source4_digest="a" * 64,
        rollback_backup_digest="f" * 64,
    )
    replay = await executor.execute(
        repository,
        manifest=plan.manifest,
        expected_base_source4_digest="a" * 64,
        rollback_backup_digest="f" * 64,
    )
    assert first == replay
    assert first.counts == {"updated": 1, "held": 1, "created": 1}
    assert repository.states[changed.key].source_digest == "2" * 64
    assert repository.states[created.key].source_digest == "4" * 64
    assert repository.states[conflict.key].source_digest == "6" * 64
