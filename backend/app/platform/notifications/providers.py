from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class NotificationMessage:
    notification_id: UUID
    notification_type: str
    template_identifier: str
    recipient: str
    payload: dict[str, object]
    correlation_id: UUID


@dataclass(frozen=True)
class NotificationDeliveryResult:
    provider_message_id: str | None = None


class NotificationProvider(Protocol):
    """Future provider boundary; implementations must not own persistence."""

    async def deliver(
        self, message: NotificationMessage
    ) -> NotificationDeliveryResult: ...
