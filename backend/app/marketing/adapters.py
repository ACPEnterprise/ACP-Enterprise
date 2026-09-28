from datetime import datetime

from .contracts import ProviderSnapshotEnvelope


class FixtureMarketingProviderAdapter:
    """Deterministic test/development adapter with no network or mutation surface."""

    def __init__(
        self,
        *,
        provider_family: str,
        adapter_version: str,
        records: tuple[ProviderSnapshotEnvelope, ...] = (),
    ) -> None:
        self.provider_family = provider_family
        self.adapter_version = adapter_version
        self._records = records

    async def snapshots(
        self,
        *,
        external_account_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> tuple[ProviderSnapshotEnvelope, ...]:
        del external_account_id
        return tuple(
            item
            for item in self._records
            if (start_at is None or item.provider_as_of >= start_at)
            and (end_at is None or item.provider_as_of <= end_at)
        )
