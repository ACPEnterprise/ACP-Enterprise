from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timezone

from ..domain import ProviderKey, canonical_digest
from .contract import (
    AcquisitionCursor,
    AdapterContext,
    AdapterControls,
    ProviderCapability,
    ProviderDiscovery,
    ProviderPage,
)


class ReadOnlySkeletonAdapter:
    """Safe adapter boundary until provider credentials and approval exist."""

    provider = ProviderKey("unconfigured")
    capabilities: tuple[ProviderCapability, ...] = ()
    controls = AdapterControls(True, True, True, True, True, "polling_backfill")

    def __init__(
        self, fixture_pages: Mapping[str, tuple[ProviderPage, ...]] | None = None
    ) -> None:
        self.fixture_pages = dict(fixture_pages or {})

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
        pages = self.fixture_pages.get(cursor.family)
        if pages is None:
            raise RuntimeError(f"{self.provider}: live read authorization required")
        start = cursor.page_identity
        emit = start is None
        for page in pages:
            if not emit and page.cursor.page_identity == start:
                emit = True
            if emit:
                yield page
        if start is not None and not emit:
            raise RuntimeError(f"{self.provider}: resume cursor not found")

    async def acquire_delta(
        self, context: AdapterContext, cursor: AcquisitionCursor
    ) -> AsyncIterator[ProviderPage]:
        async for page in self.acquire_full(context, cursor):
            yield page
