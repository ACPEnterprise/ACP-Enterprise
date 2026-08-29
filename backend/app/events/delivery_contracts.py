from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ConsumerMode(StrEnum):
    IDEMPOTENT_REPLAY_SAFE = "idempotent_replay_safe"
    IDEMPOTENT_ORDERED = "idempotent_ordered"
    READ_MODEL_PULL = "read_model_pull"
    EXTERNAL = "external"
    EXCLUDED = "excluded"


@dataclass(frozen=True, order=True)
class ConsumerDefinition:
    name: str
    mode: ConsumerMode
    supported_versions: frozenset[str]
    evidence: str
    event_types: frozenset[str] = frozenset()

    @property
    def requires_delivery(self) -> bool:
        return self.mode in {
            ConsumerMode.IDEMPOTENT_REPLAY_SAFE,
            ConsumerMode.IDEMPOTENT_ORDERED,
            ConsumerMode.EXTERNAL,
        }


CONSUMER_REGISTRY = (
    ConsumerDefinition(
        "analytics.business_event_queries",
        ConsumerMode.READ_MODEL_PULL,
        frozenset({"1.0"}),
        "app.analytics.service reads Company-scoped immutable events",
    ),
    ConsumerDefinition(
        "beacon.event_evidence_queries",
        ConsumerMode.READ_MODEL_PULL,
        frozenset({"1.0"}),
        "app.beacon.repository reads Company-scoped event evidence",
    ),
    ConsumerDefinition(
        "communications.source_event_queries",
        ConsumerMode.READ_MODEL_PULL,
        frozenset({"1.0"}),
        "app.communications.repository binds source events by Company and Branch",
    ),
    ConsumerDefinition(
        "customers.timeline_queries",
        ConsumerMode.READ_MODEL_PULL,
        frozenset({"1.0"}),
        "app.customers.timeline reads Company-scoped immutable events",
    ),
)


def event_version(payload: dict[str, object]) -> str:
    value = payload.get("schema_version", "1.0")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Business Event schema version is invalid.")
    return value


def consumer_definition(name: str) -> ConsumerDefinition:
    try:
        return next(item for item in CONSUMER_REGISTRY if item.name == name)
    except StopIteration as exc:
        raise ValueError("Business Event consumer is not registered.") from exc


def delivery_consumers(event_type: str) -> tuple[ConsumerDefinition, ...]:
    return tuple(
        item
        for item in CONSUMER_REGISTRY
        if item.requires_delivery and event_type in item.event_types
    )
