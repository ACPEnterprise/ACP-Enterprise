from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayExecutor,
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayDomainHold,
    OverlayExecutionReceipt,
    OverlayKey,
    OverlayRecord,
    OverlaySourceState,
)
from app.operational_migration.hcp_current_overlay_native import (
    HcpCurrentOverlayNativeServices,
    _bounded_hold_code,
)

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64
BACKUP = "c" * 64
ACQUIRED = "2026-09-12T16:49:00+00:00"


def test_bounded_hold_code_preserves_deterministic_trace_suffix() -> None:
    reason = "held because required parent is non-operational: service_location:" + (
        "a" * 80
    )
    bounded = _bounded_hold_code(reason)

    assert len(bounded) == 100
    assert bounded.startswith(reason[:87])
    assert bounded[-13] == "~"
    assert _bounded_hold_code(reason) == bounded


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
        state = OverlaySourceState(
            record.source_digest, f"native-{record.source_id}", record.payload
        )
        self.states[record.key] = state
        return state

    async def update(
        self, state: OverlaySourceState, record: OverlayRecord
    ) -> OverlaySourceState:
        updated = OverlaySourceState(
            record.source_digest, state.native_id, record.payload
        )
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
    domain: str = "job",
    source_digest: str = DIGEST,
    prior: str | None = None,
    parents: tuple[OverlayKey, ...] = (),
    fingerprint: str | None = None,
) -> OverlayRecord:
    return OverlayRecord(
        domain,
        source_id,
        assertion,
        source_digest,
        ACQUIRED,
        {}
        if assertion in {OverlayAssertion.HOLD, OverlayAssertion.REMOVE}
        else {"status": "ready"},
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


def test_hcp_source4_namespace_is_distinct_from_legacy_hcp_namespace() -> None:
    value = manifest(record("cus_namespace", OverlayAssertion.CREATE, domain="customer"))

    assert value.source_system == "housecall_pro_source4"
    with pytest.raises(ValueError, match="current overlay digest mismatch"):
        replace(value, source_system="housecall_pro").verify()


@pytest.mark.asyncio
async def test_customer_name_projection_uses_authoritative_person_name() -> None:
    customer_id = uuid4()
    customer = SimpleNamespace(
        id=customer_id,
        company_id="company",
        updated_at=datetime(2026, 11, 19, tzinfo=timezone.utc),
    )
    updates = AsyncMock()
    updates.stage_update.return_value = customer
    services = object.__new__(HcpCurrentOverlayNativeServices)
    services.context = SimpleNamespace(company=SimpleNamespace(id="company"))
    services.customer_updates = updates
    session = SimpleNamespace(get=AsyncMock(return_value=customer))
    record_value = OverlayRecord(
        "customer",
        "cus_projection",
        OverlayAssertion.UPDATE,
        DIGEST,
        ACQUIRED,
        {
            # This was the historical failure mode: a stale tenant display name
            # must never replace the source person's authoritative name.
            "display_name": "All County Plumbing and Leak",
            "first_name": "Richard",
            "last_name": "Ratliff",
            "updated_at": "2026-11-20T00:00:00+00:00",
        },
    )

    await services._update_customer(
        session,
        OverlaySourceState(DIGEST, str(customer_id), {}),
        record_value,
    )

    request = updates.stage_update.call_args.kwargs["data"]
    assert request.display_name == "Richard Ratliff"
    assert request.display_name != record_value.payload["display_name"]


@pytest.mark.asyncio
async def test_newer_native_customer_change_is_held_without_overwrite() -> None:
    customer_id = uuid4()
    customer = SimpleNamespace(
        id=customer_id,
        company_id="company",
        updated_at=datetime(2026, 11, 21, tzinfo=timezone.utc),
    )
    updates = AsyncMock()
    services = object.__new__(HcpCurrentOverlayNativeServices)
    services.context = SimpleNamespace(company=SimpleNamespace(id="company"))
    services.customer_updates = updates
    session = SimpleNamespace(get=AsyncMock(return_value=customer))
    record_value = OverlayRecord(
        "customer",
        "cus_newer_native",
        OverlayAssertion.UPDATE,
        DIGEST,
        ACQUIRED,
        {
            "first_name": "Source",
            "last_name": "Value",
            "updated_at": "2026-11-20T00:00:00+00:00",
        },
    )

    with pytest.raises(OverlayDomainHold, match="newer native Customer state"):
        await services._update_customer(
            session,
            OverlaySourceState(DIGEST, str(customer_id), {}),
            record_value,
        )
    updates.stage_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_customer_match_is_held_and_replay_does_not_mutate() -> None:
    repository = MemoryRepository()
    value = manifest(
        OverlayRecord(
            "customer",
            "cus_ambiguous",
            OverlayAssertion.HOLD,
            DIGEST,
            ACQUIRED,
            {},
            reason="ambiguous_identity_review_required",
        ),
        record("cus_safe", OverlayAssertion.CREATE, domain="customer"),
    )

    first = await CurrentOverlayExecutor().execute(
        repository,
        manifest=value,
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
        executable_domains=frozenset({"customer"}),
    )
    replay = await CurrentOverlayExecutor().execute(
        repository,
        manifest=value,
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
        executable_domains=frozenset({"customer"}),
    )

    assert first == replay
    assert first.counts == {"held": 1, "created": 1}
    assert OverlayKey("customer", "cus_ambiguous") not in repository.states
    assert [item.reason for item in repository.assertions] == [
        "ambiguous_identity_review_required"
    ]


@pytest.mark.asyncio
async def test_customer_roster_admission_is_independent_of_jobs_and_accounting() -> None:
    repository = MemoryRepository()
    value = manifest(record("cus_roster_only", OverlayAssertion.CREATE, domain="customer"))

    receipt = await CurrentOverlayExecutor().execute(
        repository,
        manifest=value,
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
        executable_domains=frozenset({"customer"}),
    )

    assert receipt.counts == {"created": 1}
    assert repository.states[OverlayKey("customer", "cus_roster_only")].native_id == (
        "native-cus_roster_only"
    )
    assert not any(key.domain in {"job", "estimate", "invoice", "payment"} for key in repository.states)


@pytest.mark.asyncio
async def test_executes_create_update_hold_and_removal_with_replay() -> None:
    repository = MemoryRepository()
    existing = OverlayKey("job", "existing")
    repository.states[existing] = OverlaySourceState(
        DIGEST, "native-existing", {"status": "draft"}
    )
    value = manifest(
        record("new", OverlayAssertion.CREATE),
        record(
            "existing",
            OverlayAssertion.UPDATE,
            source_digest=OTHER_DIGEST,
            prior=DIGEST,
        ),
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
    assert first.counts == {
        "created": 1,
        "updated": 1,
        "held": 1,
        "removal_recorded": 1,
    }
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
            manifest=manifest(
                record("existing", OverlayAssertion.UPDATE, prior=OTHER_DIGEST)
            ),
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
            manifest=manifest(
                record("new", OverlayAssertion.CREATE, fingerprint=OTHER_DIGEST)
            ),
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

    held_parent = record("parent", OverlayAssertion.HOLD)
    child = record(
        "child",
        OverlayAssertion.CREATE,
        parents=(held_parent.key,),
    )
    receipt = await CurrentOverlayExecutor().execute(
        repository,
        manifest=manifest(held_parent, child),
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
    )
    assert receipt.counts == {"held": 2}
    assert [item.reason for item in repository.assertions] == [
        "",
        "held because required parent is non-operational: job:parent",
    ]


@pytest.mark.asyncio
async def test_applies_parent_domains_before_children_when_packet_is_child_first() -> (
    None
):
    repository = MemoryRepository()
    customer = record("customer", OverlayAssertion.CREATE, domain="customer")
    location = record(
        "location",
        OverlayAssertion.CREATE,
        domain="service_location",
        parents=(customer.key,),
    )
    job = record(
        "job",
        OverlayAssertion.CREATE,
        parents=(customer.key, location.key),
    )
    appointment = record(
        "appointment",
        OverlayAssertion.CREATE,
        domain="appointment",
        parents=(job.key,),
    )

    receipt = await CurrentOverlayExecutor().execute(
        repository,
        manifest=manifest(appointment, job, location, customer),
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
    )

    assert [item.key.domain for item in receipt.journal] == [
        "customer",
        "service_location",
        "job",
        "appointment",
    ]


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


def test_private_manifest_round_trip_and_tamper_rejection(tmp_path: Path) -> None:
    path = tmp_path / "overlay.json"
    value = manifest(record("new", OverlayAssertion.CREATE))
    path.write_text(json.dumps(value.private_payload()))
    assert CurrentOverlayManifest.load(path) == value
    path.write_text(json.dumps(value.private_payload() | {"digest": OTHER_DIGEST}))
    with pytest.raises(ValueError, match="digest mismatch"):
        CurrentOverlayManifest.load(path)


@pytest.mark.asyncio
async def test_expected_domain_conflict_is_held_without_hiding_other_work() -> None:
    class HoldingRepository(MemoryRepository):
        async def create(self, record: OverlayRecord) -> OverlaySourceState:
            if record.source_id == "held-by-domain":
                raise OverlayDomainHold("lifecycle conflict")
            return await super().create(record)

    repository = HoldingRepository()
    receipt = await CurrentOverlayExecutor().execute(
        repository,
        manifest=manifest(
            record("held-by-domain", OverlayAssertion.CREATE),
            record("safe", OverlayAssertion.CREATE),
        ),
        expected_base_source4_digest=DIGEST,
        rollback_backup_digest=BACKUP,
    )

    assert receipt.counts == {"held": 1, "created": 1}
    assert [item.source_id for item in repository.assertions] == ["held-by-domain"]
