"""Explicit provider-neutral delivery boundary for the durable notification outbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.notifications.models import NotificationOutbox
from app.platform.notifications.providers import (
    NotificationDeliveryResult,
    NotificationMessage,
    NotificationProvider,
    NotificationProviderOutcome,
)
from app.platform.notifications.repository import NotificationOutboxRepository

from .templates import RenderedTransactionalMessage


class TransactionalContentResolver(Protocol):
    async def render(
        self, record: NotificationOutbox
    ) -> RenderedTransactionalMessage: ...


class ProviderWebhookVerifier(Protocol):
    def verify(self, *, headers: dict[str, str], body: bytes) -> bool: ...


@dataclass(frozen=True)
class ProviderDeliveryEvent:
    company_id: UUID
    provider_reference: str
    provider_event_key: str
    outcome: str
    occurred_at: datetime
    safe_error_code: str | None = None


class ProviderWebhookService:
    async def ingest(
        self,
        session: AsyncSession,
        *,
        verifier: ProviderWebhookVerifier,
        headers: dict[str, str],
        body: bytes,
        event: ProviderDeliveryEvent,
    ) -> bool:
        if not verifier.verify(headers=headers, body=body):
            raise ValueError("Provider event authenticity could not be established.")
        return await NotificationOutboxRepository.apply_provider_event(
            session,
            company_id=event.company_id,
            provider_reference=event.provider_reference,
            provider_event_key=event.provider_event_key,
            outcome=event.outcome,
            at=event.occurred_at,
            error_code=event.safe_error_code,
        )


@dataclass(frozen=True)
class DeliveryDisposition:
    notification_id: str
    outcome: str
    provider_reference: str | None


class TransactionalDeliveryService:
    """Executes one already-claimed item; scheduling remains externally owned."""

    async def deliver_claimed(
        self,
        session: AsyncSession,
        *,
        record: NotificationOutbox,
        provider: NotificationProvider,
        resolver: TransactionalContentResolver,
        now: datetime,
        retry_at: datetime | None = None,
    ) -> DeliveryDisposition:
        if record.status != "claimed" or record.claim_token is None:
            raise ValueError("Transactional delivery requires a durable claim.")
        rendered = await resolver.render(record)
        if rendered.template_version != (
            record.template_version or record.template_identifier
        ):
            raise ValueError(
                "Transactional template version does not match durable intent."
            )
        result = await provider.deliver(
            NotificationMessage(
                notification_id=record.id,
                notification_type=record.notification_type,
                template_identifier=record.template_identifier,
                recipient=record.recipient,
                payload={},
                correlation_id=record.correlation_id,
                subject=rendered.subject,
                plain_text=rendered.plain_text,
                html=rendered.html,
                content_digest=rendered.content_digest,
                provider_idempotency_key=record.provider_idempotency_key,
            )
        )
        if (
            result.outcome
            in {
                NotificationProviderOutcome.ACCEPTED,
                NotificationProviderOutcome.DELIVERED,
            }
            and not result.provider_message_id
        ):
            result = NotificationDeliveryResult(
                outcome=NotificationProviderOutcome.UNCERTAIN,
                error_code="provider_reference_missing",
            )
        await self._persist_result(
            session, record=record, result=result, now=now, retry_at=retry_at
        )
        return DeliveryDisposition(
            str(record.id), result.outcome.value, result.provider_message_id
        )

    @staticmethod
    async def _persist_result(
        session: AsyncSession,
        *,
        record: NotificationOutbox,
        result: NotificationDeliveryResult,
        now: datetime,
        retry_at: datetime | None,
    ) -> None:
        token = record.claim_token
        assert token is not None
        if result.outcome in {
            NotificationProviderOutcome.ACCEPTED,
            NotificationProviderOutcome.DELIVERED,
        }:
            await NotificationOutboxRepository.record_provider_submission(
                session,
                notification_id=record.id,
                claim_token=token,
                submitted_at=now,
                provider_reference=result.provider_message_id,
            )
            if result.outcome is NotificationProviderOutcome.DELIVERED:
                await NotificationOutboxRepository.mark_sent(
                    session, notification_id=record.id, claim_token=token, sent_at=now
                )
            else:
                await NotificationOutboxRepository.mark_accepted(
                    session, notification_id=record.id, claim_token=token, at=now
                )
            return
        if result.outcome is NotificationProviderOutcome.UNCERTAIN:
            if record.submitted_at is None:
                await NotificationOutboxRepository.record_provider_submission(
                    session,
                    notification_id=record.id,
                    claim_token=token,
                    submitted_at=now,
                    provider_reference=result.provider_message_id,
                )
            await NotificationOutboxRepository.mark_ambiguous(
                session,
                notification_id=record.id,
                claim_token=token,
                error_code=result.error_code or "provider_outcome_uncertain",
                at=now,
            )
            return
        if result.outcome is NotificationProviderOutcome.DEFERRED and result.retryable:
            scheduled = retry_at or now + timedelta(minutes=5)
            ok = await NotificationOutboxRepository.schedule_retry(
                session,
                notification_id=record.id,
                claim_token=token,
                scheduled_at=scheduled,
                error_code=result.error_code or "provider_deferred",
                error_category="transient",
                now=now,
            )
            if ok:
                return
        await NotificationOutboxRepository.mark_failed(
            session,
            notification_id=record.id,
            claim_token=token,
            error_code=result.error_code or result.outcome.value,
            error_category="permanent",
            failed_at=now,
        )


class SyntheticNotificationProvider:
    """Deterministic non-network qualification adapter."""

    def __init__(self, outcome: NotificationProviderOutcome) -> None:
        self.outcome = outcome
        self.messages: list[NotificationMessage] = []

    async def deliver(self, message: NotificationMessage) -> NotificationDeliveryResult:
        self.messages.append(message)
        return NotificationDeliveryResult(
            outcome=self.outcome,
            provider_message_id=f"synthetic:{message.notification_id}",
            error_code=None
            if self.outcome
            in {
                NotificationProviderOutcome.ACCEPTED,
                NotificationProviderOutcome.DELIVERED,
            }
            else f"synthetic_{self.outcome.value}",
            retryable=self.outcome is NotificationProviderOutcome.DEFERRED,
        )
