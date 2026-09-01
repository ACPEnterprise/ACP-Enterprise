from dataclasses import dataclass
from enum import StrEnum
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
    subject: str = ""
    plain_text: str = ""
    html: str = ""
    content_digest: str = ""
    provider_idempotency_key: str | None = None


class NotificationProviderOutcome(StrEnum):
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    BOUNCED = "bounced"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class NotificationDeliveryResult:
    outcome: NotificationProviderOutcome
    provider_message_id: str | None = None
    error_code: str | None = None
    retryable: bool = False


class NotificationProvider(Protocol):
    """Future provider boundary; implementations must not own persistence."""

    async def deliver(
        self, message: NotificationMessage
    ) -> NotificationDeliveryResult: ...
