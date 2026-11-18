from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import MigrationFactoryError, ProviderKey
from .contract import ProviderAdapter


@dataclass(slots=True)
class ProviderRegistry:
    _adapters: dict[ProviderKey, ProviderAdapter] = field(default_factory=dict)

    def register(self, adapter: ProviderAdapter) -> None:
        if adapter.provider in self._adapters:
            raise MigrationFactoryError(
                f"provider already registered: {adapter.provider}"
            )
        self._adapters[adapter.provider] = adapter

    def get(self, provider: ProviderKey) -> ProviderAdapter:
        try:
            return self._adapters[provider]
        except KeyError as error:
            raise MigrationFactoryError(
                f"provider not registered: {provider}"
            ) from error

    def keys(self) -> tuple[ProviderKey, ...]:
        return tuple(sorted(self._adapters))


def default_registry() -> ProviderRegistry:
    from .housecall_pro import HousecallProAdapter
    from .jobber import JobberAdapter
    from .quickbooks import QuickBooksAdapter
    from .sage import SageAdapter
    from .servicetitan import ServiceTitanAdapter
    from .structured_file import StructuredFileAdapter
    from .xero import XeroAdapter

    registry = ProviderRegistry()
    for adapter_type in (
        HousecallProAdapter,
        ServiceTitanAdapter,
        JobberAdapter,
        QuickBooksAdapter,
        XeroAdapter,
        SageAdapter,
        StructuredFileAdapter,
    ):
        registry.register(adapter_type())
    return registry
