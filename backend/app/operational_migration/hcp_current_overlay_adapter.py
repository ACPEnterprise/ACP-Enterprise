"""SQLAlchemy persistence adapter for the HCP current-overlay executor.

Native mutations are delegated to the existing migration/domain-service facade; this
adapter owns transactionality, master-run locking, compare state, provenance, holds,
fingerprint ownership, and the durable replay receipt.  No raw SQL mutation bypasses
the domain boundaries.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.hcp_current_overlay import (
    EXECUTOR_CONTRACT,
    CurrentOverlayRepository,
    OverlayExecutionReceipt,
    OverlayJournalEntry,
    OverlayKey,
    OverlayRecord,
    OverlaySourceState,
)
from app.operational_migration.models import HcpMigrationMasterRun

STATE_KEY = "hcp_current_overlay"


class CurrentOverlayDomainServices(Protocol):
    """Existing authoritative domain-service composition used by the adapter."""

    async def create(
        self, session: AsyncSession, record: OverlayRecord
    ) -> OverlaySourceState: ...

    async def update(
        self,
        session: AsyncSession,
        state: OverlaySourceState,
        record: OverlayRecord,
    ) -> OverlaySourceState: ...

    async def source_state(
        self, session: AsyncSession, key: OverlayKey
    ) -> OverlaySourceState | None: ...

    async def source_exists(self, session: AsyncSession, key: OverlayKey) -> bool: ...

    async def fingerprint_owners(
        self, session: AsyncSession, domain: str, fingerprint: str
    ) -> tuple[str, ...]: ...

    async def record_non_mutating_assertion(
        self, session: AsyncSession, record: OverlayRecord
    ) -> None: ...


class SqlAlchemyCurrentOverlayRepository(CurrentOverlayRepository):
    """Durable, lock-protected adapter bound to one admitted SOURCE.4 master run."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        master_run_id: UUID,
        services: CurrentOverlayDomainServices,
    ) -> None:
        self._session = session
        self._master_run_id = master_run_id
        self._services = services
        self._master: HcpMigrationMasterRun | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        if self._session.in_transaction():
            raise ValueError("overlay adapter requires ownership of its transaction")
        async with self._session.begin():
            self._master = await self._session.scalar(
                select(HcpMigrationMasterRun)
                .where(HcpMigrationMasterRun.id == self._master_run_id)
                .with_for_update()
            )
            if self._master is None or self._master.status != "completed":
                raise ValueError("completed SOURCE.4 master run is required")
            yield
            self._master = None

    async def prior_receipt(
        self, manifest_digest: str
    ) -> OverlayExecutionReceipt | None:
        value = self._state()["receipts"].get(manifest_digest)
        if value is None:
            return None
        return _receipt(value)

    async def source_state(self, key: OverlayKey) -> OverlaySourceState | None:
        cached = self._state()["source_states"].get(_key(key))
        if cached is not None:
            return OverlaySourceState(**cast(dict[str, Any], cached))
        return await self._services.source_state(self._session, key)

    async def source_exists(self, key: OverlayKey) -> bool:
        return await self.source_state(key) is not None or await self._services.source_exists(
            self._session, key
        )

    async def fingerprint_owners(
        self, domain: str, fingerprint: str
    ) -> tuple[str, ...]:
        durable = cast(
            list[str],
            self._state()["fingerprints"].get(f"{domain}:{fingerprint}", []),
        )
        existing = await self._services.fingerprint_owners(
            self._session, domain, fingerprint
        )
        return tuple(sorted(set(durable) | set(existing)))

    async def create(self, record: OverlayRecord) -> OverlaySourceState:
        state = await self._services.create(self._session, record)
        self._record_state(record, state)
        return state

    async def update(
        self, state: OverlaySourceState, record: OverlayRecord
    ) -> OverlaySourceState:
        updated = await self._services.update(self._session, state, record)
        if updated.native_id != state.native_id:
            raise ValueError("overlay update cannot replace native identity")
        self._record_state(record, updated)
        return updated

    async def record_non_mutating_assertion(self, record: OverlayRecord) -> None:
        await self._services.record_non_mutating_assertion(self._session, record)
        assertions = self._state()["assertions"]
        value = asdict(record)
        existing = assertions.get(_key(record.key))
        if existing is not None and existing != value:
            raise ValueError("overlay assertion replay conflict")
        assertions[_key(record.key)] = value
        self._write_state()

    async def persist_receipt(self, receipt: OverlayExecutionReceipt) -> None:
        if receipt.contract != EXECUTOR_CONTRACT:
            raise ValueError("overlay receipt contract mismatch")
        receipts = self._state()["receipts"]
        value = asdict(receipt)
        existing = receipts.get(receipt.manifest_digest)
        if existing is not None and existing != value:
            raise ValueError("overlay receipt replay conflict")
        receipts[receipt.manifest_digest] = value
        self._write_state()

    def _record_state(
        self, record: OverlayRecord, state: OverlaySourceState
    ) -> None:
        values = self._state()
        values["source_states"][_key(record.key)] = asdict(state)
        if record.native_fingerprint:
            values["fingerprints"][
                f"{record.domain}:{record.native_fingerprint}"
            ] = [state.native_id]
        self._write_state()

    def _state(self) -> dict[str, Any]:
        if self._master is None:
            raise ValueError("overlay adapter used outside transaction")
        root = dict(self._master.replay_state)
        value = root.get(STATE_KEY)
        if not isinstance(value, dict):
            value = {
                "receipts": {},
                "source_states": {},
                "fingerprints": {},
                "assertions": {},
            }
            root[STATE_KEY] = value
            self._master.replay_state = root
        return value

    def _write_state(self) -> None:
        if self._master is None:
            raise ValueError("overlay adapter used outside transaction")
        # Assign a fresh root so SQLAlchemy JSON mutation tracking is deterministic.
        root = dict(self._master.replay_state)
        root[STATE_KEY] = dict(cast(dict[str, Any], root[STATE_KEY]))
        self._master.replay_state = root


def _key(key: OverlayKey) -> str:
    return f"{key.domain}:{key.source_id}"


def _receipt(value: object) -> OverlayExecutionReceipt:
    if not isinstance(value, dict):
        raise TypeError("stored overlay receipt is invalid")
    journal = tuple(
        OverlayJournalEntry(
            key=OverlayKey(**item["key"]),
            assertion=item["assertion"],
            outcome=item["outcome"],
            before_digest=item.get("before_digest"),
            after_digest=item.get("after_digest"),
            native_id=item.get("native_id"),
        )
        for item in value["journal"]
    )
    return OverlayExecutionReceipt(
        contract=value["contract"],
        manifest_digest=value["manifest_digest"],
        rollback_backup_digest=value["rollback_backup_digest"],
        counts=value["counts"],
        journal=journal,
        digest=value["digest"],
    )
