from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import case, delete, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.notifications.models import NotificationOutbox


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
    ) -> tuple[NotificationOutbox, bool]:
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
        return existing, False

    @staticmethod
    async def load_pending_work(
        session: AsyncSession,
        *,
        now: datetime,
        limit: int,
        after_id: UUID | None = None,
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
    ) -> list[NotificationOutbox]:
        records = list(
            (
                await session.scalars(
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
            ).all()
        )
        for record in records:
            record.status = "claimed"
            record.claimed_at = now
            record.claimed_by = worker_id
            record.claim_token = uuid4()
            record.updated_at = now
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
        result = await session.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.id == notification_id,
                NotificationOutbox.status == "claimed",
                NotificationOutbox.claim_token == claim_token,
            )
            .values(
                status="sent",
                claim_token=None,
                sent_at=sent_at,
                terminal_failure=False,
                last_error_code=None,
                last_error_category=None,
                updated_at=sent_at,
            )
        )
        return bool(cast(CursorResult[Any], result).rowcount)

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
        result = await session.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.id == notification_id,
                NotificationOutbox.status == "claimed",
                NotificationOutbox.claim_token == claim_token,
            )
            .values(
                status="failed",
                claim_token=None,
                failed_at=failed_at,
                terminal_failure=True,
                retry_count=NotificationOutbox.retry_count + 1,
                last_error_code=error_code,
                last_error_category=error_category,
                updated_at=failed_at,
            )
        )
        return bool(cast(CursorResult[Any], result).rowcount)

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
        result = await session.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.id == notification_id,
                NotificationOutbox.status == "claimed",
                NotificationOutbox.claim_token == claim_token,
            )
            .values(
                status="retry_scheduled",
                retry_count=NotificationOutbox.retry_count + 1,
                scheduled_at=scheduled_at,
                claimed_at=None,
                claimed_by=None,
                claim_token=None,
                last_error_code=error_code,
                last_error_category=error_category,
                updated_at=now,
            )
        )
        return bool(cast(CursorResult[Any], result).rowcount)

    @staticmethod
    async def release_abandoned_claims(
        session: AsyncSession,
        *,
        claimed_before: datetime,
        release_at: datetime,
    ) -> int:
        result = await session.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.status == "claimed",
                NotificationOutbox.claimed_at <= claimed_before,
            )
            .values(
                status=case(
                    (NotificationOutbox.retry_count > 0, "retry_scheduled"),
                    else_="pending",
                ),
                scheduled_at=release_at,
                claimed_at=None,
                claimed_by=None,
                claim_token=None,
                updated_at=release_at,
            )
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    @staticmethod
    async def cleanup_completed_notifications(
        session: AsyncSession,
        *,
        completed_before: datetime,
        limit: int,
    ) -> int:
        candidates = (
            select(NotificationOutbox.id)
            .where(
                NotificationOutbox.status.in_(("sent", "failed")),
                NotificationOutbox.updated_at < completed_before,
            )
            .order_by(NotificationOutbox.updated_at, NotificationOutbox.id)
            .limit(limit)
        )
        result = await session.execute(
            delete(NotificationOutbox).where(NotificationOutbox.id.in_(candidates))
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)


notification_outbox_repository = NotificationOutboxRepository()
