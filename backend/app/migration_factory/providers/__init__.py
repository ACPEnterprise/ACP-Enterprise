"""Read-only provider plugins for the Migration Factory."""

from .contract import (
    AcquisitionCursor,
    AdapterContext,
    CapabilityState,
    ProviderAdapter,
    ProviderCapability,
    ProviderDiscovery,
    ProviderPage,
    ProviderRawRecord,
)
from .registry import ProviderRegistry, default_registry

__all__ = [
    "AcquisitionCursor",
    "AdapterContext",
    "CapabilityState",
    "ProviderAdapter",
    "ProviderCapability",
    "ProviderDiscovery",
    "ProviderPage",
    "ProviderRawRecord",
    "ProviderRegistry",
    "default_registry",
]
