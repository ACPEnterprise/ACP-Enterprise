import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .runtime import (
    ProviderCredentialResolution,
    ProviderCredentialStatus,
)


class ProviderCredentialMaterial:
    """Ephemeral secret material with an intentionally redacted representation."""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        self.__value = value

    def reveal_for_provider_initialization(self) -> str:
        return self.__value

    def __repr__(self) -> str:
        return "ProviderCredentialMaterial([REDACTED])"

    __str__ = __repr__


@dataclass(frozen=True)
class EnvironmentCredentialResolver:
    variable_name: str = "OPENAI_API_KEY"
    environment: Mapping[str, str] | None = None

    async def resolve(
        self,
        *,
        company_id: UUID,
        worker_id: UUID,
        provider_identifier: str,
        now: datetime,
    ) -> ProviderCredentialResolution:
        del company_id, worker_id, now
        source = self.environment if self.environment is not None else os.environ
        value = source.get(self.variable_name, "")
        if not value:
            return ProviderCredentialResolution(
                status=ProviderCredentialStatus.UNAVAILABLE,
                credential_reference=None,
                expires_at=None,
                material=None,
            )
        return ProviderCredentialResolution(
            status=ProviderCredentialStatus.USABLE,
            credential_reference=f"environment:{self.variable_name}",
            expires_at=None,
            material=ProviderCredentialMaterial(value),
        )
