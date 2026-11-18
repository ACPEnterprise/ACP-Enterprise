from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

from ..domain import ProviderKey, canonical_digest
from .contract import (
    AcquisitionCursor,
    AdapterContext,
    ProviderCapability,
    ProviderDiscovery,
    ProviderPage,
)


class ReadOnlySkeletonAdapter:
    """Safe adapter boundary until provider credentials and approval exist."""

    provider = ProviderKey("unconfigured")
    capabilities: tuple[ProviderCapability, ...] = ()

    async def discover(self, context: AdapterContext) -> ProviderDiscovery:
        return ProviderDiscovery(
            self.provider,
            canonical_digest(context.connection_reference),
            (),
            self.capabilities,
            {},
            {},
            datetime.now(timezone.utc),
        )

    async def acquire_full(
        self, context: AdapterContext, cursor: AcquisitionCursor
    ) -> AsyncIterator[ProviderPage]:
        if False:
            yield  # pragma: no cover
        raise RuntimeError(f"{self.provider}: live read authorization required")

    async def acquire_delta(
        self, context: AdapterContext, cursor: AcquisitionCursor
    ) -> AsyncIterator[ProviderPage]:
        if False:
            yield  # pragma: no cover
        raise RuntimeError(f"{self.provider}: delta authorization required")
