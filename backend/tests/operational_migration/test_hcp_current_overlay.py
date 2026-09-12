from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayExecutor,
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayExecutionReceipt,
    OverlayKey,
    OverlayRecord,
    OverlaySourceState,
)

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64
BACKUP = "c" * 64
ACQUIRED = "2026-09-12T16:49:00+00:00"


class MemoryRepository:
    def __init__(self) -> None:
        self.states: dict[OverlayKey, OverlaySourceState] = {}
        self.receipts: dict[str, OverlayExecutionReceipt] = {}
        self.assertions: list[OverlayRecord] = []
        self.fingerprints: dict[tuple[str, str], tuple[str, ...]] = {}
        self.transaction_entries = 0

    @asynccontextmanager
    async def transaction(self):  # type: ignore[no-untyped-def]
        self.transaction_entries += 1
        yield

    async def prior_receipt(self, manifest_digest: str):  # type: ignore[no-untyped-def]
        return self.receipts.get(manifest_digest)

    async def source_state(self, key: OverlayKey):  # type: ignore[no-untyped-def]
        return self.states.get(key)

    async def source_exists(self, key: OverlayKey) -> bool:
        return key in self.states

    async def fingerprint_owners(self, domain: str, fingerprint: str):  # type: ignore[no-untyped-def]
        return self.fingerprints.get((domain, fingerprint), ())

    async def create(self, record: OverlayRecord) -> OverlaySourceState:
        state = OverlaySourceState(record.source_digest, f"native-{record.source_id}", record.payload)
        self.states[record.key] = state
        return state

    async def update(
        self, state: OverlaySourceState, record: OverlayRecord
    ) -> OverlaySourceState:
        updated = OverlaySourceState(record.source_digest, state.native_id, record.payload)
        self.states[record.key] = updated
        return updated

    async def record_non_mutating_assertion(self, record: OverlayRecord) -> None:
        self.assertions.append(record)

    async def persist_receipt(self, receipt: OverlayExecutionReceipt) -> None:
        self.receipts[receipt.manifest_digest] = receipt


def record(
    source_id: str,
    assertion: OverlayAssertion,
    *,
    source_digest: str = DIGEST,
    prior: str | None = None,
    parents: tuple[OverlayKey, ...] = (),
    fingerprint: str | None = None,
) -> OverlayRecord:
    return OverlayRecord(
        "job",
        source_id,
        assertion,
        source_digest,
        ACQUIRED,
        {} if assertion in {OverlayAssertion.HOLD, OverlayAssertion.REMOVE} else {"status": "ready"},
        prior,
        parents,
        fingerprint,
    )


def manifest(*records: OverlayRecord) -> CurrentOverlayManifest:
    return CurrentOverlayManifest.build(
        base_source4_digest=DIGEST,
        delta_digest=OTHER_DIGEST,
        company_id="company",
        branch_id="branch",
        acquired_at=ACQUIRED,
        records=records,
    )


@pytest.mark.asyncio
async def test_executes_create_update_hold_and_removal_with_replay() -> None:
    repository = MemoryRepository()
    existing = OverlayKey("job", "existing")
    repository.states[existing] = OverlaySourceState(DIGEST, "native-existing", {"status": "draft"})
    value = manifest(
        record("new", OverlayAssertion.CREATE),
        record("existing", OverlayAssertion.UPDATE, source_digest=OTHER_DIGEST, prior=DIGEST),
        record("held", OverlayAssertion.HOLD),
        record("removed", OverlayAssertion.REMOVE),
    )

    executor = CurrentOverlayExecutor()
    first = await executor.execute(
        repository,
        manifest=value,
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
    )
    replay = await executor.execute(
        repository,
        manifest=value,
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
    )

    assert first == replay
    assert repository.transaction_entries == 2
    assert first.counts == {"created": 1, "updated": 1, "held": 1, "removal_recorded": 1}
    assert len(repository.assertions) == 2


@pytest.mark.asyncio
async def test_rejects_stale_update_and_duplicate_create() -> None:
    repository = MemoryRepository()
    repository.states[OverlayKey("job", "existing")] = OverlaySourceState(
        DIGEST, "native-existing", {}
    )
    with pytest.raises(ValueError, match="compare-before-write"):
        await CurrentOverlayExecutor().execute(
            repository,
            manifest=manifest(record("existing", OverlayAssertion.UPDATE, prior=OTHER_DIGEST)),
            expected_base_source4_digest=DIGEST,
            rollback_backup_digest=BACKUP,
        )

    repository.fingerprints[("job", OTHER_DIGEST)] = ("some-other-native",)
    with pytest.raises(ValueError, match="duplicate native truth"):
        await CurrentOverlayExecutor().execute(
            repository,
            manifest=manifest(
                record(
                    "existing",
                    OverlayAssertion.UPDATE,
                    source_digest=OTHER_DIGEST,
                    prior=DIGEST,
                    fingerprint=OTHER_DIGEST,
                )
            ),
            expected_base_source4_digest=DIGEST,
            rollback_backup_digest=BACKUP,
        )

    repository.fingerprints[("job", OTHER_DIGEST)] = ("native-owner",)
    with pytest.raises(ValueError, match="duplicate native truth"):
        await CurrentOverlayExecutor().execute(
            repository,
            manifest=manifest(record("new", OverlayAssertion.CREATE, fingerprint=OTHER_DIGEST)),
            expected_base_source4_digest=DIGEST,
            rollback_backup_digest=BACKUP,
        )


@pytest.mark.asyncio
async def test_requires_parent_closure_and_matching_authority() -> None:
    repository = MemoryRepository()
    child = record(
        "child",
        OverlayAssertion.CREATE,
        parents=(OverlayKey("customer", "missing"),),
    )
    with pytest.raises(ValueError, match="parent source identity missing"):
        await CurrentOverlayExecutor().execute(
            repository,
            manifest=manifest(child),
            expected_base_source4_digest=DIGEST,
            rollback_backup_digest=BACKUP,
        )
    with pytest.raises(ValueError, match="base SOURCE.4 authority"):
        await CurrentOverlayExecutor().execute(
            repository,
            manifest=manifest(record("new", OverlayAssertion.CREATE)),
            expected_base_source4_digest=OTHER_DIGEST,
            rollback_backup_digest=BACKUP,
        )


def test_manifest_is_immutable_and_rejects_invalid_assertions() -> None:
    value = manifest(record("new", OverlayAssertion.CREATE))
    value.verify()
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(value, delta_digest=DIGEST).verify()
    with pytest.raises(ValueError, match="cannot carry write payload"):
        manifest(
            OverlayRecord(
                "job",
                "held",
                OverlayAssertion.HOLD,
                DIGEST,
                ACQUIRED,
                {"unsafe": True},
            )
        )
