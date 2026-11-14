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
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

CONTRACT = "hcp-current-overlay/v1"
EXECUTOR_CONTRACT = "hcp-current-overlay-executor/v1"
OPERATIONAL_DOMAINS = frozenset({"customer", "service_location", "job", "appointment"})
# A sealed handoff may contain held historical, financial, note, attachment, and
# provider-specific identities for which ACP has no native write service.  Those
# identities are still part of the accounting surface of the receipt.  Domain
# services, rather than this structural manifest, decide which non-held records
# are executable.
SUPPORTED_DOMAINS = OPERATIONAL_DOMAINS | {"estimate", "invoice", "payment"}


class OverlayAssertion(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    REMOVE = "remove"
    HOLD = "hold"


class OverlayDomainHold(ValueError):
    """A deterministic domain conflict that must be journaled without mutation."""


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
    # Preserve the source disposition separately from the native assertion.
    source_disposition: str | None = None

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

    @classmethod
    def load(cls, path: Path) -> CurrentOverlayManifest:
        """Load and cryptographically verify a private executable overlay packet."""
        value = json.loads(path.read_bytes())
        records = tuple(
            OverlayRecord(
                domain=item["domain"],
                source_id=item["source_id"],
                assertion=OverlayAssertion(item["assertion"]),
                source_digest=item["source_digest"],
                acquired_at=item["acquired_at"],
                payload=item["payload"],
                prior_source_digest=item.get("prior_source_digest"),
                parent_keys=tuple(
                    OverlayKey(**parent) for parent in item["parent_keys"]
                ),
                native_fingerprint=item.get("native_fingerprint"),
                reason=item.get("reason", ""),
                source_disposition=item.get("source_disposition"),
            )
            for item in value["records"]
        )
        manifest = cls(
            contract=value["contract"],
            source_system=value["source_system"],
            base_source4_digest=value["base_source4_digest"],
            delta_digest=value["delta_digest"],
            company_id=value["company_id"],
            branch_id=value["branch_id"],
            acquired_at=value["acquired_at"],
            records=records,
            digest=value["digest"],
        )
        manifest.verify()
        return manifest

    def private_payload(self) -> dict[str, object]:
        """Return the complete executable packet; callers must protect source data."""
        self.verify()
        return _manifest_payload(
            self.base_source4_digest,
            self.delta_digest,
            self.company_id,
            self.branch_id,
            self.acquired_at,
            self.records,
        ) | {"digest": self.digest}


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
    native_action: str | None = None


@dataclass(frozen=True)
class OverlayExecutionReceipt:
    contract: str
    manifest_digest: str
    rollback_backup_digest: str
    counts: dict[str, int]
    journal: tuple[OverlayJournalEntry, ...]
    digest: str
    execution_context: Mapping[str, object] = field(default_factory=dict)


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
        require_non_mutating_parents: bool = True,
        execution_context: Mapping[str, object]
        | Callable[[OverlayExecutionReceipt], Mapping[str, object]]
        | None = None,
        executable_domains: frozenset[str] | None = None,
        allow_clean_baseline_bootstrap: bool = False,
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

            receipt = await self._apply(
                repository,
                manifest,
                rollback_backup_digest,
                require_non_mutating_parents=require_non_mutating_parents,
                executable_domains=executable_domains,
                allow_clean_baseline_bootstrap=allow_clean_baseline_bootstrap,
            )
            if execution_context is not None:
                context = (
                    execution_context(receipt)
                    if callable(execution_context)
                    else execution_context
                )
                receipt = _with_execution_context(receipt, context)
            await repository.persist_receipt(receipt)
            return receipt

    async def _apply(
        self,
        repository: CurrentOverlayRepository,
        manifest: CurrentOverlayManifest,
        rollback_backup_digest: str,
        *,
        require_non_mutating_parents: bool,
        executable_domains: frozenset[str] | None,
        allow_clean_baseline_bootstrap: bool,
    ) -> OverlayExecutionReceipt:
        keys = {item.key for item in manifest.records}
        blocked_keys = {
            item.key
            for item in manifest.records
            if item.assertion in {OverlayAssertion.HOLD, OverlayAssertion.REMOVE}
        }
        if executable_domains is not None:
            for item in manifest.records:
                if item.assertion not in {OverlayAssertion.HOLD, OverlayAssertion.REMOVE} and item.domain not in executable_domains:
                    raise ValueError(f"overlay executable domain is unsupported: {item.domain}")

        ordered_records = _dependency_order(manifest.records)
        journal: list[OverlayJournalEntry] = []
        for record in ordered_records:
            for parent in record.parent_keys:
                if (
                    record.assertion
                    in {
                        OverlayAssertion.CREATE,
                        OverlayAssertion.UPDATE,
                    }
                    and parent in blocked_keys
                ):
                    raise ValueError(
                        "overlay parent is non-operational: "
                        f"{record.domain}:{record.source_id} <- {parent.domain}:{parent.source_id}"
                    )
                if (
                    parent not in keys
                    and (
                        require_non_mutating_parents
                        or record.assertion
                        not in {OverlayAssertion.HOLD, OverlayAssertion.REMOVE}
                    )
                    and not await repository.source_exists(parent)
                ):
                    raise ValueError("overlay parent source identity missing")
            state = await repository.source_state(record.key)
            if record.assertion is OverlayAssertion.CREATE:
                after: OverlaySourceState | None
                action: str | None
                if state is not None:
                    if state.source_digest != record.source_digest:
                        raise ValueError("overlay create conflicts with native truth")
                    outcome = "idempotent_replay"
                    action = "REPLAY_NOOP"
                    after = state
                else:
                    source_disposition = (record.source_disposition or "CREATE").upper()
                    if source_disposition in {"UPDATE", "REPLAY"}:
                        if not allow_clean_baseline_bootstrap:
                            raise ValueError("clean-baseline bootstrap authority is required")
                        action = (
                            "BOOTSTRAP_CREATE_FROM_UPDATE"
                            if source_disposition == "UPDATE"
                            else "BOOTSTRAP_CREATE_FROM_REPLAY"
                        )
                    else:
                        action = "CREATE_NATIVE"
                    if record.native_fingerprint:
                        owners = await repository.fingerprint_owners(
                            record.domain, record.native_fingerprint
                        )
                        if owners:
                            raise ValueError("overlay duplicate native truth risk")
                    try:
                        after = await repository.create(record)
                        outcome = "created"
                    except OverlayDomainHold as error:
                        await repository.record_non_mutating_assertion(
                            replace(
                                record,
                                assertion=OverlayAssertion.HOLD,
                                payload={},
                                reason=str(error),
                            )
                        )
                        blocked_keys.add(record.key)
                        after = state
                        outcome = "held"
                        action = None
                journal.append(
                    OverlayJournalEntry(
                        record.key,
                        record.assertion,
                        outcome,
                        state.source_digest if state else None,
                        after.source_digest if after else None,
                        after.native_id if after else None,
                        action,
                    )
                )
            elif record.assertion is OverlayAssertion.UPDATE:
                if state is None and (record.source_disposition or "").upper() == "UPDATE":
                    if not allow_clean_baseline_bootstrap:
                        raise ValueError("clean-baseline bootstrap authority is required")
                    try:
                        after = await repository.create(record)
                        outcome = "bootstrapped"
                        action = "BOOTSTRAP_CREATE_FROM_UPDATE"
                    except OverlayDomainHold as error:
                        await repository.record_non_mutating_assertion(
                            replace(record, assertion=OverlayAssertion.HOLD, payload={}, reason=str(error))
                        )
                        blocked_keys.add(record.key)
                        after = state
                        outcome = "held"
                        action = None
                    journal.append(
                        OverlayJournalEntry(
                            record.key,
                            record.assertion,
                            outcome,
                            None,
                            after.source_digest if after else None,
                            after.native_id if after else None,
                            action,
                        )
                    )
                    continue
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
                    action = "REPLAY_NOOP"
                else:
                    try:
                        after = await repository.update(state, record)
                        outcome = "updated"
                    except OverlayDomainHold as error:
                        await repository.record_non_mutating_assertion(
                            replace(
                                record,
                                assertion=OverlayAssertion.HOLD,
                                payload={},
                                reason=str(error),
                            )
                        )
                        blocked_keys.add(record.key)
                        after = state
                        outcome = "held"
                        action = None
                    else:
                        action = "UPDATE_NATIVE"
                journal.append(
                    OverlayJournalEntry(
                        record.key,
                        record.assertion,
                        outcome,
                        state.source_digest,
                        after.source_digest,
                        after.native_id,
                        action,
                    )
                )
            else:
                await repository.record_non_mutating_assertion(record)
                journal.append(
                    OverlayJournalEntry(
                        record.key,
                        record.assertion,
                        "held"
                        if record.assertion is OverlayAssertion.HOLD
                        else "removal_recorded",
                        state.source_digest if state else None,
                        state.source_digest if state else None,
                        state.native_id if state else None,
                        None,
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


def _dependency_order(
    records: tuple[OverlayRecord, ...],
) -> tuple[OverlayRecord, ...]:
    """Order every domain by local parent dependencies, then deterministically."""
    by_key = {record.key: record for record in records}
    children: dict[OverlayKey, set[OverlayKey]] = {key: set() for key in by_key}
    indegree: dict[OverlayKey, int] = {key: 0 for key in by_key}
    for record in records:
        for parent in record.parent_keys:
            if parent in by_key and record.key not in children[parent]:
                children[parent].add(record.key)
                indegree[record.key] += 1

    ready = sorted(
        (key for key, degree in indegree.items() if degree == 0),
        key=lambda key: (key.domain, key.source_id),
    )
    ordered: list[OverlayRecord] = []
    while ready:
        key = ready.pop(0)
        ordered.append(by_key[key])
        for child in sorted(children[key], key=lambda value: (value.domain, value.source_id)):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=lambda value: (value.domain, value.source_id))
    if len(ordered) != len(records):
        raise ValueError("overlay parent dependency cycle")
    return tuple(ordered)


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
        if not item.domain or not item.domain.strip() or not item.source_id:
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
        if (
            item.assertion in {OverlayAssertion.REMOVE, OverlayAssertion.HOLD}
            and item.payload
        ):
            raise ValueError(
                "non-mutating overlay assertions cannot carry write payload"
            )


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
    if receipt.execution_context:
        payload["execution_context"] = dict(receipt.execution_context)
    if (
        receipt.contract == EXECUTOR_CONTRACT
        and receipt.manifest_digest == manifest_digest
        and receipt.rollback_backup_digest == rollback_backup_digest
        and receipt.digest == _digest(payload)
    ):
        return
    # Older SQL-backed receipts were persisted with an adapter-only
    # update_binding_inventory field appended after the receipt digest was
    # calculated.  Accept that known, non-semantic extension while continuing
    # to reject any other receipt tampering; new receipts are stored exactly as
    # hashed.
    context = payload.get("execution_context")
    if isinstance(context, dict) and "update_binding_inventory" in context:
        legacy_payload = dict(payload)
        legacy_payload["execution_context"] = {
            key: value
            for key, value in context.items()
            if key != "update_binding_inventory"
        }
        if receipt.digest == _digest(legacy_payload):
            return
    raise ValueError("overlay replay receipt mismatch")


def _with_execution_context(
    receipt: OverlayExecutionReceipt, context: Mapping[str, object]
) -> OverlayExecutionReceipt:
    payload = {
        "contract": receipt.contract,
        "manifest_digest": receipt.manifest_digest,
        "rollback_backup_digest": receipt.rollback_backup_digest,
        "counts": receipt.counts,
        "journal": [asdict(item) for item in receipt.journal],
        "execution_context": dict(context),
    }
    return replace(
        receipt,
        execution_context=dict(context),
        digest=_digest(payload),
    )


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
