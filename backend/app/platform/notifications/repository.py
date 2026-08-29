import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.notifications.models import (
    NotificationDeliveryEvidence,
    NotificationOutbox,
)


def _intent_digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class NotificationOutboxRepository:
    """Owns durable notification SQL, locking, and persistence transitions."""

    @staticmethod
    async def enqueue(
        session: AsyncSession,
        *,
        notification_type: str,
        template_identifier: str,
        recipient: str,
        payload: dict[str, object],
        correlation_id: UUID,
        idempotency_key: str,
        scheduled_at: datetime,
        now: datetime,
        company_id: UUID | None = None,
        branch_id: UUID | None = None,
        channel: str | None = None,
        recipient_reference: str | None = None,
        source_event_id: UUID | None = None,
        source_action: str | None = None,
        template_version: str | None = None,
        actor_user_id: UUID | None = None,
        provider_supports_idempotency: bool = False,
    ) -> tuple[NotificationOutbox, bool]:
        facts: dict[str, object] = {
            "notification_type": notification_type,
            "template_identifier": template_identifier,
            "template_version": template_version or template_identifier,
            "recipient": recipient,
            "recipient_reference": recipient_reference,
            "payload": payload,
            "correlation_id": correlation_id,
            "company_id": company_id,
            "branch_id": branch_id,
            "channel": channel,
            "source_event_id": source_event_id,
            "source_action": source_action,
            "actor_user_id": actor_user_id,
            "scheduled_at": scheduled_at,
        }
        digest = _intent_digest(facts)
        statement = (
            insert(NotificationOutbox)
            .values(
                id=uuid4(),
                notification_type=notification_type,
                template_identifier=template_identifier,
                recipient=recipient,
                payload=payload,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                intent_digest=digest,
                company_id=company_id,
                branch_id=branch_id,
                channel=channel,
                recipient_reference=recipient_reference,
                source_event_id=source_event_id,
                source_action=source_action,
                template_version=template_version or template_identifier,
                actor_user_id=actor_user_id,
                provider_supports_idempotency=provider_supports_idempotency,
                provider_idempotency_key=(
                    idempotency_key if provider_supports_idempotency else None
                ),
                status="pending",
                retry_count=0,
                terminal_failure=False,
                scheduled_at=scheduled_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(NotificationOutbox)
        )
        record = (await session.scalars(statement)).one_or_none()
        if record is not None:
            return record, True
        existing = await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise RuntimeError("Idempotent notification enqueue did not resolve.")
        legacy_match = (
            existing.intent_digest is None
            and existing.notification_type == notification_type
            and existing.template_identifier == template_identifier
            and existing.recipient == recipient
            and existing.payload == payload
            and existing.correlation_id == correlation_id
            and existing.scheduled_at == scheduled_at
        )
        if existing.intent_digest != digest and not legacy_match:
            raise ValueError(
                "Notification idempotency identity is bound to contradictory intent."
            )
        return existing, False

    @staticmethod
    async def load_pending_work(
        session: AsyncSession,
        *,
        now: datetime,
        limit: int,
        after_id: UUID | None = None,
        company_id: UUID | None = None,
        branch_id: UUID | None = None,
    ) -> list[NotificationOutbox]:
        statement = (
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status.in_(("pending", "retry_scheduled")),
                NotificationOutbox.scheduled_at <= now,
            )
            .order_by(
                NotificationOutbox.scheduled_at,
                NotificationOutbox.created_at,
                NotificationOutbox.id,
            )
            .limit(limit)
        )
        if company_id is not None:
            statement = statement.where(NotificationOutbox.company_id == company_id)
        if branch_id is not None:
            statement = statement.where(NotificationOutbox.branch_id == branch_id)
        if after_id is not None:
            anchor = (
                await session.execute(
                    select(
                        NotificationOutbox.scheduled_at,
                        NotificationOutbox.created_at,
                        NotificationOutbox.id,
                    ).where(NotificationOutbox.id == after_id)
                )
            ).one_or_none()
            if anchor is None:
                return []
            anchor_scheduled_at, anchor_created_at, anchor_record_id = anchor
            statement = statement.where(
                tuple_(
                    NotificationOutbox.scheduled_at,
                    NotificationOutbox.created_at,
                    NotificationOutbox.id,
                )
                > tuple_(anchor_scheduled_at, anchor_created_at, anchor_record_id)
            )
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def claim_batch(
        session: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        limit: int,
        claim_ttl: timedelta = timedelta(minutes=5),
        company_id: UUID | None = None,
        branch_id: UUID | None = None,
    ) -> list[NotificationOutbox]:
        statement = (
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status.in_(("pending", "retry_scheduled")),
                NotificationOutbox.scheduled_at <= now,
            )
            .order_by(
                NotificationOutbox.scheduled_at,
                NotificationOutbox.created_at,
                NotificationOutbox.id,
            )
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        if company_id is not None:
            statement = statement.where(NotificationOutbox.company_id == company_id)
        if branch_id is not None:
            statement = statement.where(NotificationOutbox.branch_id == branch_id)
        records = list((await session.scalars(statement)).all())
        for record in records:
            record.status = "claimed"
            record.claimed_at = now
            record.claim_expires_at = now + claim_ttl
            record.claimed_by = worker_id
            record.claim_token = uuid4()
            record.updated_at = now
            await NotificationOutboxRepository._evidence(
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
    async def mark_sent(
        session: AsyncSession,
        *,
        notification_id: UUID,
        claim_token: UUID,
        sent_at: datetime,
    ) -> bool:
        record = await NotificationOutboxRepository._claimed(
            session, notification_id, claim_token
        )
        if record is None:
            return False
        await NotificationOutboxRepository._evidence(
            session,
            record,
            "delivered",
            sent_at,
            worker_id=record.claimed_by,
            claim_token=claim_token,
            provider_reference=record.provider_reference,
        )
        record.status = "sent"
        record.sent_at = sent_at
        record.claimed_at = None
        record.claim_expires_at = None
        record.claimed_by = None
        record.claim_token = None
        record.terminal_failure = False
        record.last_error_code = None
        record.last_error_category = None
        record.updated_at = sent_at
        await session.flush()
        return True

    @staticmethod
    async def record_provider_submission(
        session: AsyncSession,
        *,
        notification_id: UUID,
        claim_token: UUID,
        submitted_at: datetime,
        provider_reference: str | None,
    ) -> bool:
        record = await NotificationOutboxRepository._claimed(
            session, notification_id, claim_token
        )
        if record is None:
            return False
        if record.submitted_at is not None:
            return record.provider_reference == provider_reference
        record.submitted_at = submitted_at
        record.provider_reference = provider_reference
        record.updated_at = submitted_at
        await NotificationOutboxRepository._evidence(
            session,
            record,
            "submitted",
            submitted_at,
            worker_id=record.claimed_by,
            claim_token=claim_token,
            provider_reference=provider_reference,
        )
        await session.flush()
        return True

    @staticmethod
    async def mark_ambiguous(
        session: AsyncSession,
        *,
        notification_id: UUID,
        claim_token: UUID,
        error_code: str,
        at: datetime,
    ) -> bool:
        record = await NotificationOutboxRepository._claimed(
            session, notification_id, claim_token
        )
        if record is None or record.submitted_at is None:
            return False
        await NotificationOutboxRepository._evidence(
            session,
            record,
            "ambiguous",
            at,
            worker_id=record.claimed_by,
            claim_token=claim_token,
            provider_reference=record.provider_reference,
            error_code=error_code,
            error_category="indeterminate",
        )
        record.status = "ambiguous"
        record.ambiguous_at = at
        record.claimed_at = None
        record.claim_expires_at = None
        record.claimed_by = None
        record.claim_token = None
        record.last_error_code = error_code
        record.last_error_category = "indeterminate"
        record.updated_at = at
        await session.flush()
        return True

    @staticmethod
    async def mark_failed(
        session: AsyncSession,
        *,
        notification_id: UUID,
        claim_token: UUID,
        error_code: str,
        error_category: str,
        failed_at: datetime,
    ) -> bool:
        record = await NotificationOutboxRepository._claimed(
            session, notification_id, claim_token
        )
        if record is None:
            return False
        await NotificationOutboxRepository._evidence(
            session,
            record,
            "failed",
            failed_at,
            worker_id=record.claimed_by,
            claim_token=claim_token,
            error_code=error_code,
            error_category=error_category,
        )
        record.status = "failed"
        record.failed_at = failed_at
        record.terminal_failure = True
        record.retry_count += 1
        record.last_error_code = error_code
        record.last_error_category = error_category
        record.claimed_at = None
        record.claim_expires_at = None
        record.claimed_by = None
        record.claim_token = None
        record.updated_at = failed_at
        await session.flush()
        return True

    @staticmethod
    async def schedule_retry(
        session: AsyncSession,
        *,
        notification_id: UUID,
        claim_token: UUID,
        scheduled_at: datetime,
        error_code: str,
        error_category: str,
        now: datetime,
    ) -> bool:
        record = await NotificationOutboxRepository._claimed(
            session, notification_id, claim_token
        )
        if record is None or scheduled_at <= now:
            return False
        if record.submitted_at is not None and not record.provider_supports_idempotency:
            return False
        await NotificationOutboxRepository._evidence(
            session,
            record,
            "retryable",
            now,
            worker_id=record.claimed_by,
            claim_token=claim_token,
            provider_reference=record.provider_reference,
            error_code=error_code,
            error_category=error_category,
        )
        record.status = "retry_scheduled"
        record.retry_count += 1
        record.scheduled_at = scheduled_at
        record.claimed_at = None
        record.claim_expires_at = None
        record.claimed_by = None
        record.claim_token = None
        record.last_error_code = error_code
        record.last_error_category = error_category
        record.updated_at = now
        await session.flush()
        return True

    @staticmethod
    async def release_abandoned_claims(
        session: AsyncSession,
        *,
        claimed_before: datetime,
        release_at: datetime,
    ) -> int:
        records = tuple(
            (
                await session.scalars(
                    select(NotificationOutbox)
                    .where(
                        NotificationOutbox.status == "claimed",
                        NotificationOutbox.claimed_at <= claimed_before,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for record in records:
            prior_worker = record.claimed_by
            prior_token = record.claim_token
            if (
                record.submitted_at is not None
                and not record.provider_supports_idempotency
            ):
                outcome = "ambiguous"
                error_code = "claim_expired_after_submission"
                next_status = "ambiguous"
            else:
                next_status = "retry_scheduled" if record.retry_count > 0 else "pending"
                outcome = "recovered"
                error_code = None
            await NotificationOutboxRepository._evidence(
                session,
                record,
                outcome,
                release_at,
                worker_id=prior_worker,
                claim_token=prior_token,
                provider_reference=record.provider_reference,
                error_code=error_code,
                error_category="indeterminate" if error_code else None,
            )
            record.status = next_status
            if next_status == "ambiguous":
                record.ambiguous_at = release_at
            else:
                record.scheduled_at = release_at
            record.claimed_at = None
            record.claim_expires_at = None
            record.claimed_by = None
            record.claim_token = None
            record.updated_at = release_at
        await session.flush()
        return len(records)

    @staticmethod
    async def cleanup_completed_notifications(
        session: AsyncSession,
        *,
        completed_before: datetime,
        limit: int,
    ) -> int:
        records = tuple(
            (
                await session.scalars(
                    select(NotificationOutbox)
                    .where(
                        NotificationOutbox.status.in_(("sent", "failed")),
                        NotificationOutbox.updated_at < completed_before,
                        NotificationOutbox.archived_at.is_(None),
                    )
                    .order_by(NotificationOutbox.updated_at, NotificationOutbox.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for record in records:
            record.archived_at = completed_before
        await session.flush()
        return len(records)

    @staticmethod
    async def suppress_or_cancel(
        session: AsyncSession,
        *,
        notification_id: UUID,
        target: str,
        actor_user_id: UUID,
        reason_digest: str,
        authorized: bool,
        now: datetime,
    ) -> bool:
        if not authorized or target not in {"suppressed", "canceled"}:
            return False
        if len(reason_digest) != 64:
            raise ValueError("Notification disposition reason must be SHA-256.")
        record = await session.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.id == notification_id,
                NotificationOutbox.status.in_(("pending", "retry_scheduled")),
            )
            .with_for_update()
        )
        if record is None:
            return False
        record.status = target
        record.updated_at = now
        await NotificationOutboxRepository._evidence(
            session,
            record,
            target,
            now,
            actor_user_id=actor_user_id,
            reason_digest=reason_digest,
        )
        await session.flush()
        return True

    @staticmethod
    async def _claimed(
        session: AsyncSession, notification_id: UUID, claim_token: UUID
    ) -> NotificationOutbox | None:
        return await session.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.id == notification_id,
                NotificationOutbox.status == "claimed",
                NotificationOutbox.claim_token == claim_token,
            )
            .with_for_update()
        )

    @staticmethod
    async def _evidence(
        session: AsyncSession,
        record: NotificationOutbox,
        outcome: str,
        at: datetime,
        *,
        worker_id: str | None = None,
        claim_token: UUID | None = None,
        provider_reference: str | None = None,
        error_code: str | None = None,
        error_category: str | None = None,
        actor_user_id: UUID | None = None,
        reason_digest: str | None = None,
    ) -> None:
        sequence = await session.scalar(
            select(
                func.coalesce(func.max(NotificationDeliveryEvidence.sequence), 0)
            ).where(NotificationDeliveryEvidence.outbox_id == record.id)
        )
        session.add(
            NotificationDeliveryEvidence(
                outbox_id=record.id,
                sequence=int(sequence or 0) + 1,
                outcome=outcome,
                company_id=record.company_id,
                branch_id=record.branch_id,
                worker_id=worker_id,
                claim_token=claim_token,
                provider_reference=provider_reference,
                error_code=error_code,
                error_category=error_category,
                actor_user_id=actor_user_id,
                reason_digest=reason_digest,
                recorded_at=at,
            )
        )
        await session.flush()


notification_outbox_repository = NotificationOutboxRepository()
