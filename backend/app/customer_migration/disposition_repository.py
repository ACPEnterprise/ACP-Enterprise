from typing import Protocol
from uuid import UUID

from app.customer_migration.disposition_contracts import (
    DispositionApplicationReceipt,
    OwnerDisposition,
)


class OwnerDispositionRepository(Protocol):
    async def get_latest(
        self,
        *,
        company_id: UUID,
        disposition_identity: str,
    ) -> OwnerDisposition | None: ...

    async def append(
        self,
        disposition: OwnerDisposition,
        *,
        expected_previous_version: int,
    ) -> OwnerDisposition: ...

    async def list_for_replay(
        self,
        *,
        company_id: UUID,
        source_artifact_sha256: str,
    ) -> tuple[OwnerDisposition, ...]: ...


class DispositionApplicationLedger(Protocol):
    async def get_receipt(
        self,
        *,
        company_id: UUID,
        application_id: str,
    ) -> DispositionApplicationReceipt | None: ...

    async def record_receipt(
        self, receipt: DispositionApplicationReceipt
    ) -> DispositionApplicationReceipt: ...
