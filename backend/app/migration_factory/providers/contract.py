"""Provider-neutral, deliberately read-only acquisition contract."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from ..domain import Domain, ProviderKey


class CapabilityState(StrEnum):
    AVAILABLE_API = "AVAILABLE_API"
    AVAILABLE_REPORT = "AVAILABLE_REPORT"
    AVAILABLE_FILE = "AVAILABLE_FILE"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    REQUIRES_UPGRADE = "REQUIRES_UPGRADE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    domain: Domain
    state: CapabilityState
    resource: str
    required_scopes: tuple[str, ...] = ()
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class AdapterControls:
    read_only: bool
    pagination: bool
    resumable: bool
    idempotent_reads: bool
    bounded_retry: bool
    delta_mode: str


@dataclass(frozen=True, slots=True)
class AdapterContext:
    company_id: str
    connection_reference: str
    authorization_reference: str


@dataclass(frozen=True, slots=True)
class ProviderDiscovery:
    provider: ProviderKey
    company_identity_digest: str
    authorized_scopes: tuple[str, ...]
    capabilities: tuple[ProviderCapability, ...]
    historical_depth: Mapping[str, str]
    api_limits: Mapping[str, str]
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class AcquisitionCursor:
    family: str
    page_identity: str | None = None
    high_water_mark: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRawRecord:
    provider: ProviderKey
    object_type: str
    object_id: str
    payload: Mapping[str, object]
    source_timestamp: datetime | None
    api_version: str


@dataclass(frozen=True, slots=True)
class ProviderPage:
    cursor: AcquisitionCursor
    records: tuple[ProviderRawRecord, ...]
    quarantined: tuple[Mapping[str, object], ...]
    next_cursor: AcquisitionCursor | None
    terminal: bool
    provider_count: int | None


class ProviderAdapter(Protocol):
    """Adapters expose reads only; source mutation is absent by construction."""

    provider: ProviderKey
    controls: AdapterControls

    async def discover(self, context: AdapterContext) -> ProviderDiscovery: ...

    def acquire_full(
        self, context: AdapterContext, cursor: AcquisitionCursor
    ) -> AsyncIterator[ProviderPage]: ...

    def acquire_delta(
        self, context: AdapterContext, cursor: AcquisitionCursor
    ) -> AsyncIterator[ProviderPage]: ...
