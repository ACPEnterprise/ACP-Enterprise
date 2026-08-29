from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.delivery_contracts import (
    ConsumerMode,
    consumer_definition,
    event_version,
)
from app.events.models import (
    BusinessEvent,
    BusinessEventConsumerCursor,
    BusinessEventConsumerReceipt,
    BusinessEventDelivery,
    BusinessEventDeliveryEvidence,
)


class DeliveryConflict(ValueError):
    pass


class BusinessEventDeliveryService:
    @staticmethod
    async def register(
        session: AsyncSession,
        *,
        event: BusinessEvent,
        consumer_name: str,
        now: datetime,
    ) -> BusinessEventDelivery:
        definition = consumer_definition(consumer_name)
        if not definition.requires_delivery:
            raise DeliveryConflict(
                "Pull/excluded consumers do not create delivery work."
            )
        version = event_version(event.payload)
        if version not in definition.supported_versions:
            raise DeliveryConflict("Unsupported Business Event version.")
        existing = await session.scalar(
            select(BusinessEventDelivery).where(
                BusinessEventDelivery.event_id == event.id,
                BusinessEventDelivery.consumer_name == consumer_name,
            )
        )
        if existing is not None:
            if existing.event_version != version:
                raise DeliveryConflict(
                    "Delivery identity has contradictory version evidence."
                )
            return existing
        delivery = BusinessEventDelivery(
            event_id=event.id,
            consumer_name=consumer_name,
            event_version=version,
            company_id=event.company_id,
            branch_id=event.branch_id,
            status="pending",
            attempt_count=0,
            replay_count=0,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(delivery)
        await session.flush()
        return delivery

    @staticmethod
    async def claim_batch(
        session: AsyncSession,
        *,
        consumer_name: str,
        company_id: UUID,
        branch_id: UUID | None,
        worker_id: str,
        now: datetime,
        claim_expires_at: datetime,
        limit: int,
    ) -> tuple[BusinessEventDelivery, ...]:
        definition = consumer_definition(consumer_name)
        if not definition.requires_delivery:
            raise DeliveryConflict("Consumer has no delivery work.")
        if not worker_id.strip() or claim_expires_at <= now or not 1 <= limit <= 200:
            raise DeliveryConflict("Delivery claim boundary is invalid.")
        records = tuple(
            (
                await session.scalars(
                    select(BusinessEventDelivery)
                    .where(
                        BusinessEventDelivery.consumer_name == consumer_name,
                        BusinessEventDelivery.company_id == company_id,
                        BusinessEventDelivery.branch_id == branch_id,
                        or_(
                            and_(
                                BusinessEventDelivery.status.in_(
                                    ("pending", "retryable")
                                ),
                                BusinessEventDelivery.next_attempt_at <= now,
                            ),
                            and_(
                                BusinessEventDelivery.status == "claimed",
                                BusinessEventDelivery.claim_expires_at <= now,
                            ),
                        ),
                    )
                    .order_by(
                        BusinessEventDelivery.next_attempt_at,
                        BusinessEventDelivery.created_at,
                        BusinessEventDelivery.id,
                    )
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            ).all()
        )
        for record in records:
            if record.status == "claimed":
                await BusinessEventDeliveryService._evidence(
                    session, record, "recovered", now, worker_id=worker_id
                )
            record.status = "claimed"
            record.attempt_count += 1
            record.claimed_at = now
            record.claim_expires_at = claim_expires_at
            record.claimed_by = worker_id
            record.claim_token = uuid4()
            record.updated_at = now
            await BusinessEventDeliveryService._evidence(
                session,
                record,
                "claimed",
                now,
                worker_id=worker_id,
                claim_token=record.claim_token,
            )
        await session.flush()
        return records

    @staticmethod
    async def record_consumer_effect(
        session: AsyncSession,
        *,
        delivery_id: UUID,
        claim_token: UUID,
        company_id: UUID,
        branch_id: UUID | None,
        outcome_digest: str,
        now: datetime,
    ) -> bool:
        delivery = await BusinessEventDeliveryService._claimed(
            session, delivery_id, claim_token, company_id, branch_id
        )
        if len(outcome_digest) != 64:
            raise DeliveryConflict("Consumer outcome digest must be SHA-256.")
        receipt = await session.scalar(
            select(BusinessEventConsumerReceipt).where(
                BusinessEventConsumerReceipt.event_id == delivery.event_id,
                BusinessEventConsumerReceipt.consumer_name == delivery.consumer_name,
            )
        )
        if receipt is not None:
            if receipt.outcome_digest != outcome_digest:
                raise DeliveryConflict("Consumer replay contradicts immutable outcome.")
            await BusinessEventDeliveryService._evidence(
                session,
                delivery,
                "idempotent",
                now,
                outcome_digest=receipt.outcome_digest,
            )
            return False
        event = await session.get(BusinessEvent, delivery.event_id)
        if (
            event is None
            or event.company_id != company_id
            or event.branch_id != branch_id
        ):
            raise DeliveryConflict("Business Event delivery scope is invalid.")
        definition = consumer_definition(delivery.consumer_name)
        sequence: int | None = None
        if definition.mode == ConsumerMode.IDEMPOTENT_ORDERED:
            sequence = event.payload.get("aggregate_sequence")  # type: ignore[assignment]
            if not isinstance(sequence, int) or sequence < 1 or event.entity_id is None:
                raise DeliveryConflict(
                    "Ordered consumer requires aggregate sequence evidence."
                )
            cursor = await session.scalar(
                select(BusinessEventConsumerCursor)
                .where(
                    BusinessEventConsumerCursor.consumer_name == delivery.consumer_name,
                    BusinessEventConsumerCursor.company_id == company_id,
                    BusinessEventConsumerCursor.entity_type == event.entity_type,
                    BusinessEventConsumerCursor.entity_id == event.entity_id,
                )
                .with_for_update()
            )
            if cursor is not None and sequence <= cursor.last_sequence:
                raise DeliveryConflict(
                    "Ordered consumer rejected stale event application."
                )
            if cursor is None:
                cursor = BusinessEventConsumerCursor(
                    consumer_name=delivery.consumer_name,
                    company_id=company_id,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    last_sequence=sequence,
                    last_event_id=event.id,
                    updated_at=now,
                )
                session.add(cursor)
            else:
                cursor.last_sequence = sequence
                cursor.last_event_id = event.id
                cursor.updated_at = now
        session.add(
            BusinessEventConsumerReceipt(
                event_id=event.id,
                consumer_name=delivery.consumer_name,
                company_id=company_id,
                branch_id=branch_id,
                outcome_digest=outcome_digest,
                aggregate_sequence=sequence,
                created_at=now,
            )
        )
        await session.flush()
        return True

    @staticmethod
    async def acknowledge(
        session: AsyncSession,
        *,
        delivery_id: UUID,
        claim_token: UUID,
        company_id: UUID,
        branch_id: UUID | None,
        now: datetime,
    ) -> BusinessEventDelivery:
        delivery = await BusinessEventDeliveryService._claimed(
            session, delivery_id, claim_token, company_id, branch_id
        )
        receipt = await session.scalar(
            select(BusinessEventConsumerReceipt).where(
                BusinessEventConsumerReceipt.event_id == delivery.event_id,
                BusinessEventConsumerReceipt.consumer_name == delivery.consumer_name,
            )
        )
        if receipt is None:
            raise DeliveryConflict(
                "Delivery cannot acknowledge before consumer receipt."
            )
        await BusinessEventDeliveryService._evidence(
            session,
            delivery,
            "delivered",
            now,
            worker_id=delivery.claimed_by,
            claim_token=delivery.claim_token,
            outcome_digest=receipt.outcome_digest,
        )
        delivery.status = "delivered"
        delivery.delivered_at = now
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        delivery.claimed_by = None
        delivery.claim_token = None
        delivery.last_error_code = None
        delivery.last_error_category = None
        delivery.updated_at = now
        await session.flush()
        return delivery

    @staticmethod
    async def fail(
        session: AsyncSession,
        *,
        delivery_id: UUID,
        claim_token: UUID,
        company_id: UUID,
        branch_id: UUID | None,
        error_code: str,
        error_category: str,
        retry_at: datetime | None,
        max_attempts: int,
        now: datetime,
    ) -> BusinessEventDelivery:
        delivery = await BusinessEventDeliveryService._claimed(
            session, delivery_id, claim_token, company_id, branch_id
        )
        if not error_code.strip() or error_category not in {"transient", "terminal"}:
            raise DeliveryConflict("Safe failure classification is required.")
        retryable = (
            error_category == "transient"
            and retry_at is not None
            and retry_at > now
            and delivery.attempt_count < max_attempts
        )
        delivery.status = "retryable" if retryable else "terminal"
        if retryable:
            assert retry_at is not None
            delivery.next_attempt_at = retry_at
        delivery.terminal_at = None if retryable else now
        delivery.last_error_code = error_code
        delivery.last_error_category = error_category
        await BusinessEventDeliveryService._evidence(
            session,
            delivery,
            "retryable" if retryable else "terminal",
            now,
            worker_id=delivery.claimed_by,
            claim_token=delivery.claim_token,
            error_code=error_code,
            error_category=error_category,
        )
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        delivery.claimed_by = None
        delivery.claim_token = None
        delivery.updated_at = now
        await session.flush()
        return delivery

    @staticmethod
    async def request_replay(
        session: AsyncSession,
        *,
        delivery_id: UUID,
        company_id: UUID,
        branch_id: UUID | None,
        actor_user_id: UUID,
        request_id: UUID,
        authorized: bool,
        now: datetime,
    ) -> BusinessEventDelivery:
        if not authorized:
            raise DeliveryConflict("Replay authority is required.")
        prior = await session.scalar(
            select(BusinessEventDeliveryEvidence).where(
                BusinessEventDeliveryEvidence.request_id == request_id
            )
        )
        if prior is not None:
            if prior.delivery_id != delivery_id or prior.actor_user_id != actor_user_id:
                raise DeliveryConflict("Replay request identity is contradictory.")
            existing = await session.get(BusinessEventDelivery, delivery_id)
            if existing is None:
                raise DeliveryConflict("Replay request has orphaned delivery evidence.")
            return existing
        delivery = await session.scalar(
            select(BusinessEventDelivery)
            .where(
                BusinessEventDelivery.id == delivery_id,
                BusinessEventDelivery.company_id == company_id,
                BusinessEventDelivery.branch_id == branch_id,
            )
            .with_for_update()
        )
        if delivery is None or delivery.status not in {"delivered", "terminal"}:
            raise DeliveryConflict("Only terminal delivery evidence may be replayed.")
        event = await session.get(BusinessEvent, delivery.event_id)
        definition = consumer_definition(delivery.consumer_name)
        if (
            event is None
            or event_version(event.payload) not in definition.supported_versions
        ):
            raise DeliveryConflict("Replay event version is unsupported or corrupt.")
        delivery.status = "pending"
        delivery.replay_count += 1
        delivery.next_attempt_at = now
        delivery.terminal_at = None
        delivery.claimed_at = None
        delivery.claim_expires_at = None
        delivery.claimed_by = None
        delivery.claim_token = None
        delivery.updated_at = now
        await BusinessEventDeliveryService._evidence(
            session,
            delivery,
            "replay_requested",
            now,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        await session.flush()
        return delivery

    @staticmethod
    async def _claimed(
        session: AsyncSession,
        delivery_id: UUID,
        claim_token: UUID,
        company_id: UUID,
        branch_id: UUID | None,
    ) -> BusinessEventDelivery:
        delivery = await session.scalar(
            select(BusinessEventDelivery)
            .where(
                BusinessEventDelivery.id == delivery_id,
                BusinessEventDelivery.company_id == company_id,
                BusinessEventDelivery.branch_id == branch_id,
            )
            .with_for_update()
        )
        if (
            delivery is None
            or delivery.status != "claimed"
            or delivery.claim_token != claim_token
        ):
            raise DeliveryConflict("Delivery claim is stale or outside scope.")
        return delivery

    @staticmethod
    async def _evidence(
        session: AsyncSession,
        delivery: BusinessEventDelivery,
        outcome: str,
        now: datetime,
        *,
        worker_id: str | None = None,
        claim_token: UUID | None = None,
        actor_user_id: UUID | None = None,
        request_id: UUID | None = None,
        error_code: str | None = None,
        error_category: str | None = None,
        outcome_digest: str | None = None,
    ) -> None:
        sequence = await session.scalar(
            select(
                func.coalesce(
                    func.max(BusinessEventDeliveryEvidence.evidence_sequence), 0
                )
            ).where(BusinessEventDeliveryEvidence.delivery_id == delivery.id)
        )
        session.add(
            BusinessEventDeliveryEvidence(
                delivery_id=delivery.id,
                event_id=delivery.event_id,
                consumer_name=delivery.consumer_name,
                company_id=delivery.company_id,
                branch_id=delivery.branch_id,
                evidence_sequence=int(sequence or 0) + 1,
                attempt_number=delivery.attempt_count,
                outcome=outcome,
                worker_id=worker_id,
                claim_token=claim_token,
                actor_user_id=actor_user_id,
                request_id=request_id,
                error_code=error_code,
                error_category=error_category,
                outcome_digest=outcome_digest,
                recorded_at=now,
            )
        )
        await session.flush()
