from app.execution_providers.contracts import (
    ExecutionProvider,
    ProviderCapabilities,
    ProviderHealth,
)
from app.execution_providers.errors import (
    DuplicateProviderError,
    ProviderNotFoundError,
)


class ExecutionProviderRegistry:
    def __init__(self, providers: tuple[ExecutionProvider, ...] = ()) -> None:
        self._providers: dict[str, ExecutionProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ExecutionProvider) -> None:
        identifier = provider.identity.identifier.strip().lower()
        if not identifier:
            raise ValueError("Provider identifier must be nonblank.")
        if identifier in self._providers:
            raise DuplicateProviderError("Provider is already registered.")
        self._providers[identifier] = provider

    def resolve(self, identifier: str) -> ExecutionProvider:
        provider = self._providers.get(identifier.strip().lower())
        if provider is None:
            raise ProviderNotFoundError("Execution provider was not found.")
        return provider

    def capabilities(self, identifier: str) -> ProviderCapabilities:
        return self.resolve(identifier).capabilities

    async def health(self, identifier: str) -> ProviderHealth:
        return await self.resolve(identifier).health()


execution_provider_registry = ExecutionProviderRegistry()
