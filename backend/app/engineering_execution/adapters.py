from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.engineering_execution.contracts import (
    EngineeringExecutionRequest,
    EngineeringExecutionResult,
)


@dataclass(frozen=True)
class EngineeringAdapterReadiness:
    ready: bool
    reason_code: str


class EngineeringExecutionAdapter(ABC):
    @property
    @abstractmethod
    def provider_identifier(self) -> str:
        """Stable provider-neutral registry identifier."""

    @abstractmethod
    async def validate_readiness(self) -> EngineeringAdapterReadiness:
        """Report readiness without starting execution."""

    @abstractmethod
    async def execute(
        self, request: EngineeringExecutionRequest
    ) -> EngineeringExecutionResult:
        """Future execution boundary; DF.5B foundation never invokes this."""


class EngineeringExecutionAdapterRegistry:
    def __init__(self, adapters: tuple[EngineeringExecutionAdapter, ...] = ()) -> None:
        resolved: dict[str, EngineeringExecutionAdapter] = {}
        for adapter in adapters:
            identifier = adapter.provider_identifier.strip()
            if not identifier or identifier in resolved:
                raise ValueError(
                    "Execution adapter identifiers must be unique and nonblank"
                )
            resolved[identifier] = adapter
        self._adapters = resolved

    def resolve(self, provider_identifier: str) -> EngineeringExecutionAdapter | None:
        return self._adapters.get(provider_identifier)


engineering_execution_adapter_registry = EngineeringExecutionAdapterRegistry()
