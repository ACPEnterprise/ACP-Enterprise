"""Explicit provider-neutral delivery boundary for the durable notification outbox."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.notifications.models import NotificationOutbox
from app.platform.notifications.providers import (
    NotificationDeliveryResult,
    NotificationMessage,
    NotificationProvider,
    NotificationProviderOutcome,
    NotificationProviderTransportError,
)
from app.platform.notifications.repository import NotificationOutboxRepository

from .suppression import (
    RecipientControlDecision,
    SuppressionScope,
    SuppressionSource,
    recipient_suppression_repository,
)
from .templates import RenderedTransactionalMessage
from .types import CommunicationChannel


class TransactionalContentResolver(Protocol):
    async def render(
        self, record: NotificationOutbox
    ) -> RenderedTransactionalMessage: ...


class ProviderWebhookVerifier(Protocol):
    def verify(self, *, headers: dict[str, str], body: bytes) -> bool: ...


class SyntheticWebhookVerifier:
    """Deterministic verifier for non-network acceptance fixtures only."""

    def verify(self, *, headers: dict[str, str], body: bytes) -> bool:
        expected = hashlib.sha256(body).hexdigest()
        supplied = headers.get("x-synthetic-signature", "")
        return hmac.compare_digest(supplied, expected)


@dataclass(frozen=True)
class ProviderDeliveryEvent:
    company_id: UUID
    provider_reference: str
    provider_event_key: str
    outcome: str
    occurred_at: datetime
    safe_error_code: str | None = None


class RecipientControlKind(StrEnum):
    OPT_OUT = "opt_out"
    OPT_IN = "opt_in"
    HELP = "help"


@dataclass(frozen=True)
class ProviderRecipientControlEvent:
    company_id: UUID
    provider_event_key: str
    destination_digest: str
    channel: str
    kind: RecipientControlKind
    occurred_at: datetime

    def validate(self) -> None:
        if self.channel != "sms":
            raise ValueError("Recipient control event channel is unsupported.")
        if len(self.destination_digest) != 64 or not all(
            character in "0123456789abcdef" for character in self.destination_digest
        ):
            raise ValueError("Recipient control destination evidence is invalid.")
        if not self.provider_event_key.strip():
            raise ValueError("Provider event identity is required.")


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

    async def ingest_recipient_control(
        self,
        session: AsyncSession,
        *,
        verifier: ProviderWebhookVerifier,
        headers: dict[str, str],
        body: bytes,
        event: ProviderRecipientControlEvent,
        recorded_at: datetime,
    ) -> bool:
        if not verifier.verify(headers=headers, body=body):
            raise ValueError("Provider event authenticity could not be established.")
        event.validate()
        if event.kind is RecipientControlKind.HELP:
            return False
        _, created = await recipient_suppression_repository.record(
            session,
            RecipientControlDecision(
                company_id=event.company_id,
                channel=CommunicationChannel.SMS,
                destination_digest=event.destination_digest,
                scope=SuppressionScope.ALL,
                source=SuppressionSource.SMS_STOP,
                active=event.kind is RecipientControlKind.OPT_OUT,
                provider_event_key=event.provider_event_key,
                source_evidence_digest=hashlib.sha256(body).hexdigest(),
                occurred_at=event.occurred_at,
                recorded_at=recorded_at,
            ),
        )
        return created


@dataclass(frozen=True)
class DeliveryDisposition:
    notification_id: str
    outcome: str
    provider_reference: str | None


class TransactionalDeliveryService:
    """Executes one already-claimed item; scheduling remains externally owned."""

    MAX_TECHNICAL_RETRIES = 5

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
        try:
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
        except NotificationProviderTransportError as error:
            result = NotificationDeliveryResult(
                outcome=(
                    NotificationProviderOutcome.UNCERTAIN
                    if error.submission_possible
                    else NotificationProviderOutcome.DEFERRED
                ),
                error_code=error.error_code,
                retryable=error.retryable and not error.submission_possible,
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
            if record.retry_count >= TransactionalDeliveryService.MAX_TECHNICAL_RETRIES:
                await NotificationOutboxRepository.mark_failed(
                    session,
                    notification_id=record.id,
                    claim_token=token,
                    error_code="technical_retry_limit_reached",
                    error_category="permanent",
                    failed_at=now,
                )
                return
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

    def __init__(
        self,
        outcome: NotificationProviderOutcome | None = None,
        *,
        transport_error: NotificationProviderTransportError | None = None,
    ) -> None:
        if (outcome is None) == (transport_error is None):
            raise ValueError("Exactly one synthetic provider result is required.")
        self.outcome = outcome
        self.transport_error = transport_error
        self.messages: list[NotificationMessage] = []

    async def deliver(self, message: NotificationMessage) -> NotificationDeliveryResult:
        self.messages.append(message)
        if self.transport_error is not None:
            raise self.transport_error
        assert self.outcome is not None
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
