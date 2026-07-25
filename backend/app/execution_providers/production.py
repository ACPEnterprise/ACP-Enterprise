from dataclasses import dataclass
from typing import Protocol

from .codex import CodexExecutionProvider, OpenAIModelsClient
from .contracts import (
    ExecutionProvider,
    ProviderCapabilities,
    ProviderCapability,
    ProviderIdentity,
)
from .credentials import EnvironmentCredentialResolver, ProviderCredentialMaterial
from .runtime import ProductionProviderRuntime


class ExecutionProviderFactory(Protocol):
    @property
    def identity(self) -> ProviderIdentity: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def create(self, material: ProviderCredentialMaterial) -> ExecutionProvider: ...


class ExecutionProviderFactoryRegistry:
    def __init__(self, factories: tuple[ExecutionProviderFactory, ...]) -> None:
        self._factories = {
            factory.identity.identifier: factory for factory in factories
        }
        if len(self._factories) != len(factories):
            raise ValueError("Provider factory identifiers must be unique.")

    def resolve(self, identifier: str) -> ExecutionProviderFactory:
        try:
            return self._factories[identifier]
        except KeyError as error:
            raise ValueError("Provider factory was not found.") from error

    def capabilities(self, identifier: str) -> ProviderCapabilities:
        return self.resolve(identifier).capabilities


@dataclass(frozen=True)
class CodexProductionConfig:
    readiness_model: str = "gpt-5.6-sol"
    base_url: str = "https://api.openai.com"
    timeout_seconds: float = 10.0
    implementation_version: str = "1"


class CodexProviderFactory:
    def __init__(self, config: CodexProductionConfig) -> None:
        self.config = config
        self._identity = ProviderIdentity(
            identifier="codex",
            display_name="Codex",
            implementation_version=config.implementation_version,
        )
        self._capabilities = ProviderCapabilities(
            (
                ProviderCapability.ENGINEERING_EXECUTE,
                ProviderCapability.VALIDATION_RUN,
            )
        )

    @property
    def identity(self) -> ProviderIdentity:
        return self._identity

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def create(self, material: ProviderCredentialMaterial) -> ExecutionProvider:
        client = OpenAIModelsClient(
            api_key=material.reveal_for_provider_initialization(),
            model=self.config.readiness_model,
            base_url=self.config.base_url,
            timeout_seconds=self.config.timeout_seconds,
        )
        return CodexExecutionProvider(
            client=client,
            model=self.config.readiness_model,
            implementation_version=self.config.implementation_version,
        )


def compose_production_runtime(
    config: CodexProductionConfig | None = None,
) -> ProductionProviderRuntime:
    factory = CodexProviderFactory(config or CodexProductionConfig())
    return ProductionProviderRuntime(
        factories=ExecutionProviderFactoryRegistry((factory,)),
        credentials=EnvironmentCredentialResolver(),
    )
