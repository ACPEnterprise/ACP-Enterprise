from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderResult:
    text: str
    provider: str
    version: str


class LiaModelProvider(Protocol):
    async def explain(self, *, question: str, evidence_summary: str) -> ProviderResult: ...


class UnconfiguredProvider:
    """Explicit provider gate; deterministic LIA remains available."""

    name = "not-configured"
    version = "none"

    async def explain(self, *, question: str, evidence_summary: str) -> ProviderResult:
        raise RuntimeError("AI_PROVIDER_NOT_CONFIGURED")
