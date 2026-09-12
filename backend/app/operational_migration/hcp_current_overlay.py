"""Replay-safe HCP current-state overlays on admitted sealed SOURCE.4 lineage.

The overlay is deliberately independent from the immutable SOURCE.4 package.  It
contains provider assertions observed later and can only be executed by a repository
that persists the returned audit journal in the same transaction as native changes.
Removal assertions never delete native truth.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

CONTRACT = "hcp-current-overlay/v1"
EXECUTOR_CONTRACT = "hcp-current-overlay-executor/v1"
OPERATIONAL_DOMAINS = frozenset(
    {"customer", "service_location", "job", "appointment"}
)
SUPPORTED_DOMAINS = OPERATIONAL_DOMAINS | {"estimate", "invoice", "payment"}


class OverlayAssertion(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    REMOVE = "remove"
    HOLD = "hold"


@dataclass(frozen=True, order=True)
class OverlayKey:
    domain: str
    source_id: str


@dataclass(frozen=True)
class OverlayRecord:
    domain: str
    source_id: str
    assertion: OverlayAssertion
    source_digest: str
    acquired_at: str
    payload: Mapping[str, object]
    prior_source_digest: str | None = None
    parent_keys: tuple[OverlayKey, ...] = ()
    native_fingerprint: str | None = None
    reason: str = ""

    @property
    def key(self) -> OverlayKey:
        return OverlayKey(self.domain, self.source_id)


@dataclass(frozen=True)
class CurrentOverlayManifest:
    contract: str
    source_system: str
    base_source4_digest: str
    delta_digest: str
    company_id: str
    branch_id: str
    acquired_at: str
    records: tuple[OverlayRecord, ...]
    digest: str

    @classmethod
    def build(
        cls,
        *,
        base_source4_digest: str,
        delta_digest: str,
        company_id: str,
        branch_id: str,
        acquired_at: str,
        records: tuple[OverlayRecord, ...],
    ) -> CurrentOverlayManifest:
        ordered = tuple(sorted(records, key=lambda item: item.key))
        _validate_manifest_values(
            base_source4_digest=base_source4_digest,
            delta_digest=delta_digest,
            company_id=company_id,
            branch_id=branch_id,
            acquired_at=acquired_at,
            records=ordered,
        )
        payload = _manifest_payload(
            base_source4_digest,
            delta_digest,
            company_id,
            branch_id,
            acquired_at,
            ordered,
        )
        return cls(
            CONTRACT,
            "housecall_pro_source4",
            base_source4_digest,
            delta_digest,
            company_id,
            branch_id,
            acquired_at,
            ordered,
            _digest(payload),
        )

    def verify(self) -> None:
        expected = CurrentOverlayManifest.build(
            base_source4_digest=self.base_source4_digest,
            delta_digest=self.delta_digest,
            company_id=self.company_id,
            branch_id=self.branch_id,
            acquired_at=self.acquired_at,
            records=self.records,
        )
        if (
            self.contract != CONTRACT
            or self.source_system != "housecall_pro_source4"
            or self.digest != expected.digest
        ):
            raise ValueError("current overlay digest mismatch")


@dataclass(frozen=True)
class OverlaySourceState:
    source_digest: str
    native_id: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class OverlayJournalEntry:
    key: OverlayKey
    assertion: OverlayAssertion
    outcome: str
    before_digest: str | None
    after_digest: str | None
    native_id: str | None


@dataclass(frozen=True)
class OverlayExecutionReceipt:
    contract: str
    manifest_digest: str
    rollback_backup_digest: str
    counts: dict[str, int]
    journal: tuple[OverlayJournalEntry, ...]
    digest: str


class CurrentOverlayRepository(Protocol):
    """Transactional persistence boundary for native state and overlay provenance."""

    def transaction(self) -> AbstractAsyncContextManager[None]: ...

    async def prior_receipt(
        self, manifest_digest: str
    ) -> OverlayExecutionReceipt | None: ...

    async def source_state(self, key: OverlayKey) -> OverlaySourceState | None: ...

    async def source_exists(self, key: OverlayKey) -> bool: ...

    async def fingerprint_owners(
        self, domain: str, fingerprint: str
    ) -> tuple[str, ...]: ...

    async def create(self, record: OverlayRecord) -> OverlaySourceState: ...

    async def update(
        self, state: OverlaySourceState, record: OverlayRecord
    ) -> OverlaySourceState: ...

    async def record_non_mutating_assertion(self, record: OverlayRecord) -> None: ...

    async def persist_receipt(self, receipt: OverlayExecutionReceipt) -> None: ...


class CurrentOverlayExecutor:
    """Apply a qualified overlay once, or replay its identical durable receipt."""

    async def execute(
        self,
        repository: CurrentOverlayRepository,
        *,
        manifest: CurrentOverlayManifest,
        expected_base_source4_digest: str,
        rollback_backup_digest: str,
    ) -> OverlayExecutionReceipt:
        manifest.verify()
        if manifest.base_source4_digest != expected_base_source4_digest:
            raise ValueError("overlay base SOURCE.4 authority mismatch")
        _require_digest(rollback_backup_digest, "rollback backup")
        async with repository.transaction():
            replay = await repository.prior_receipt(manifest.digest)
            if replay is not None:
                _verify_receipt(replay, manifest.digest, rollback_backup_digest)
                return replay

            receipt = await self._apply(repository, manifest, rollback_backup_digest)
            await repository.persist_receipt(receipt)
            return receipt

    async def _apply(
        self,
        repository: CurrentOverlayRepository,
        manifest: CurrentOverlayManifest,
        rollback_backup_digest: str,
    ) -> OverlayExecutionReceipt:
        keys = {item.key for item in manifest.records}
        journal: list[OverlayJournalEntry] = []
        for record in manifest.records:
            for parent in record.parent_keys:
                if parent not in keys and not await repository.source_exists(parent):
                    raise ValueError("overlay parent source identity missing")
            state = await repository.source_state(record.key)
            if record.assertion is OverlayAssertion.CREATE:
                if state is not None:
                    if state.source_digest != record.source_digest:
                        raise ValueError("overlay create conflicts with native truth")
                    outcome = "idempotent_replay"
                    after = state
                else:
                    if record.native_fingerprint:
                        owners = await repository.fingerprint_owners(
                            record.domain, record.native_fingerprint
                        )
                        if owners:
                            raise ValueError("overlay duplicate native truth risk")
                    after = await repository.create(record)
                    outcome = "created"
                journal.append(
                    OverlayJournalEntry(
                        record.key,
                        record.assertion,
                        outcome,
                        state.source_digest if state else None,
                        after.source_digest,
                        after.native_id,
                    )
                )
            elif record.assertion is OverlayAssertion.UPDATE:
                if state is None or record.prior_source_digest != state.source_digest:
                    raise ValueError("overlay update compare-before-write mismatch")
                if record.native_fingerprint:
                    owners = await repository.fingerprint_owners(
                        record.domain, record.native_fingerprint
                    )
                    if any(owner != state.native_id for owner in owners):
                        raise ValueError("overlay duplicate native truth risk")
                if state.source_digest == record.source_digest:
                    after = state
                    outcome = "idempotent_replay"
                else:
                    after = await repository.update(state, record)
                    outcome = "updated"
                journal.append(
                    OverlayJournalEntry(
                        record.key,
                        record.assertion,
                        outcome,
                        state.source_digest,
                        after.source_digest,
                        after.native_id,
                    )
                )
            else:
                await repository.record_non_mutating_assertion(record)
                journal.append(
                    OverlayJournalEntry(
                        record.key,
                        record.assertion,
                        "held" if record.assertion is OverlayAssertion.HOLD else "removal_recorded",
                        state.source_digest if state else None,
                        state.source_digest if state else None,
                        state.native_id if state else None,
                    )
                )

        counts = dict(Counter(item.outcome for item in journal))
        receipt_payload = {
            "contract": EXECUTOR_CONTRACT,
            "manifest_digest": manifest.digest,
            "rollback_backup_digest": rollback_backup_digest,
            "counts": counts,
            "journal": [asdict(item) for item in journal],
        }
        receipt = OverlayExecutionReceipt(
            EXECUTOR_CONTRACT,
            manifest.digest,
            rollback_backup_digest,
            counts,
            tuple(journal),
            _digest(receipt_payload),
        )
        return receipt


def _validate_manifest_values(
    *,
    base_source4_digest: str,
    delta_digest: str,
    company_id: str,
    branch_id: str,
    acquired_at: str,
    records: tuple[OverlayRecord, ...],
) -> None:
    _require_digest(base_source4_digest, "base SOURCE.4")
    _require_digest(delta_digest, "delta")
    if not company_id or not branch_id or not records:
        raise ValueError("overlay scope and records are required")
    observed = datetime.fromisoformat(acquired_at.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("overlay acquisition timestamp must be timezone-aware")
    keys = [item.key for item in records]
    if len(keys) != len(set(keys)):
        raise ValueError("overlay source identities must be unique")
    for item in records:
        if item.domain not in SUPPORTED_DOMAINS or not item.source_id:
            raise ValueError("overlay record identity is invalid")
        _require_digest(item.source_digest, "record source")
        if item.prior_source_digest is not None:
            _require_digest(item.prior_source_digest, "prior record source")
        if item.native_fingerprint is not None:
            _require_digest(item.native_fingerprint, "native fingerprint")
        record_time = datetime.fromisoformat(item.acquired_at.replace("Z", "+00:00"))
        if record_time.tzinfo is None or record_time > observed:
            raise ValueError("overlay record acquisition timestamp is invalid")
        if item.assertion is OverlayAssertion.UPDATE and not item.prior_source_digest:
            raise ValueError("overlay update requires prior source digest")
        if item.assertion in {OverlayAssertion.REMOVE, OverlayAssertion.HOLD} and item.payload:
            raise ValueError("non-mutating overlay assertions cannot carry write payload")


def _verify_receipt(
    receipt: OverlayExecutionReceipt,
    manifest_digest: str,
    rollback_backup_digest: str,
) -> None:
    payload = {
        "contract": receipt.contract,
        "manifest_digest": receipt.manifest_digest,
        "rollback_backup_digest": receipt.rollback_backup_digest,
        "counts": receipt.counts,
        "journal": [asdict(item) for item in receipt.journal],
    }
    if (
        receipt.contract != EXECUTOR_CONTRACT
        or receipt.manifest_digest != manifest_digest
        or receipt.rollback_backup_digest != rollback_backup_digest
        or receipt.digest != _digest(payload)
    ):
        raise ValueError("overlay replay receipt mismatch")


def _manifest_payload(
    base_source4_digest: str,
    delta_digest: str,
    company_id: str,
    branch_id: str,
    acquired_at: str,
    records: tuple[OverlayRecord, ...],
) -> dict[str, object]:
    return {
        "contract": CONTRACT,
        "source_system": "housecall_pro_source4",
        "base_source4_digest": base_source4_digest,
        "delta_digest": delta_digest,
        "company_id": company_id,
        "branch_id": branch_id,
        "acquired_at": acquired_at,
        "records": [asdict(item) for item in records],
    }


def _require_digest(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} digest is invalid")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{label} digest is invalid") from error


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
