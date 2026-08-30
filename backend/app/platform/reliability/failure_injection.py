from __future__ import annotations

from enum import StrEnum

from app.core.config import Settings


class FailurePoint(StrEnum):
    RESPONSE_LOST_AFTER_COMMIT = "RESPONSE_LOST_AFTER_COMMIT"
    PROVIDER_TIMEOUT_BEFORE_ACCEPTANCE = "PROVIDER_TIMEOUT_BEFORE_ACCEPTANCE"
    PROVIDER_ACCEPTANCE_UNCERTAIN = "PROVIDER_ACCEPTANCE_UNCERTAIN"
    REDIS_UNAVAILABLE = "REDIS_UNAVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"


class InjectedReliabilityFailure(RuntimeError):
    pass


def inject_failure(point: FailurePoint, configuration: Settings) -> None:
    """Deterministic test-only fault boundary, mechanically prohibited elsewhere."""
    if configuration.environment != "test":
        raise RuntimeError("failure injection is prohibited outside test")
    raise InjectedReliabilityFailure(point.value)
