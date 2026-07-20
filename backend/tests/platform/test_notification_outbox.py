import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.platform.notifications.models import NotificationOutbox
from app.platform.notifications.repository import NotificationOutboxRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def outbox_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(delete(NotificationOutbox))
    try:
        yield engine, factory
    finally:
        async with factory() as session, session.begin():
            await session.execute(delete(NotificationOutbox))
        await engine.dispose()


async def enqueue_fixture(
    factory: async_sessionmaker[AsyncSession],
    *,
    key: str | None = None,
    scheduled_at: datetime | None = None,
) -> NotificationOutbox:
    now = utc_now()
    async with factory() as session, session.begin():
        record, created = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="identity.email_change_verification",
            template_identifier="identity-email-change-verification-v1",
            recipient=f"recipient-{uuid4().hex}@example.com",
            payload={"change_id": str(uuid4())},
            correlation_id=uuid4(),
            idempotency_key=key or f"test:{uuid4()}",
            scheduled_at=scheduled_at or now,
            now=now,
        )
        assert created
        return record


@pytest.mark.asyncio
async def test_enqueue_is_hash_free_structured_and_idempotent(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    now = utc_now()
    key = f"idempotent:{uuid4()}"
    recipient = f"recipient-{uuid4().hex}@example.com"
    payload: dict[str, object] = {"change_id": str(uuid4())}
    correlation_id = uuid4()
    async with factory() as session, session.begin():
        first, first_created = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="identity.email_change_verification",
            template_identifier="identity-email-change-verification-v1",
            recipient=recipient,
            payload=payload,
            correlation_id=correlation_id,
            idempotency_key=key,
            scheduled_at=now,
            now=now,
        )
        repeated, repeated_created = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="identity.email_change_verification",
            template_identifier="identity-email-change-verification-v1",
            recipient=recipient,
            payload=payload,
            correlation_id=correlation_id,
            idempotency_key=key,
            scheduled_at=now,
            now=now,
        )

    assert first_created
    assert not repeated_created
    assert repeated.id == first.id
    assert first.payload == payload
    sensitive_field_fragments = (
        "verification_token",
        "access_token",
        "refresh_token",
        "password",
        "credential_hash",
    )
    assert not any(
        fragment in column.name
        for column in NotificationOutbox.__table__.columns
        for fragment in sensitive_field_fragments
    )

    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.idempotency_key == key)
        )
    assert count == 1


@pytest.mark.asyncio
async def test_claiming_is_ordered_and_exclusive_across_workers(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    base = utc_now() - timedelta(minutes=1)
    records = [
        await enqueue_fixture(factory, scheduled_at=base + timedelta(seconds=index))
        for index in range(4)
    ]

    ready = asyncio.Event()
    release = asyncio.Event()

    async def first_worker() -> list[NotificationOutbox]:
        async with factory() as session, session.begin():
            claimed = await NotificationOutboxRepository.claim_batch(
                session, worker_id="worker-a", now=utc_now(), limit=2
            )
            ready.set()
            await release.wait()
            return claimed

    async def second_worker() -> list[NotificationOutbox]:
        await ready.wait()
        async with factory() as session, session.begin():
            claimed = await NotificationOutboxRepository.claim_batch(
                session, worker_id="worker-b", now=utc_now(), limit=2
            )
            release.set()
            return claimed

    first, second = await asyncio.gather(first_worker(), second_worker())

    first_ids = [record.id for record in first]
    second_ids = [record.id for record in second]
    assert first_ids == [record.id for record in records[:2]]
    assert second_ids == [record.id for record in records[2:]]
    assert set(first_ids).isdisjoint(second_ids)
    assert all(record.claim_token is not None for record in first + second)


@pytest.mark.asyncio
async def test_pending_work_uses_stable_cursor_pagination(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    base = utc_now() - timedelta(minutes=1)
    records = [
        await enqueue_fixture(factory, scheduled_at=base + timedelta(seconds=index))
        for index in range(3)
    ]

    async with factory() as session:
        first_page = await NotificationOutboxRepository.load_pending_work(
            session, now=utc_now(), limit=2
        )
        second_page = await NotificationOutboxRepository.load_pending_work(
            session,
            now=utc_now(),
            limit=2,
            after_id=first_page[-1].id,
        )

    assert [record.id for record in first_page] == [
        records[0].id,
        records[1].id,
    ]
    assert [record.id for record in second_page] == [records[2].id]


@pytest.mark.asyncio
async def test_retry_failure_recovery_and_cleanup_lifecycle(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    first = await enqueue_fixture(factory)
    second = await enqueue_fixture(factory)
    now = utc_now()

    async with factory() as session, session.begin():
        claimed = await NotificationOutboxRepository.claim_batch(
            session, worker_id="worker-retry", now=now, limit=2
        )
        claim_by_id = {record.id: record.claim_token for record in claimed}
        first_claim = claim_by_id[first.id]
        second_claim = claim_by_id[second.id]
        assert first_claim is not None
        assert second_claim is not None
        assert await NotificationOutboxRepository.schedule_retry(
            session,
            notification_id=first.id,
            claim_token=first_claim,
            scheduled_at=now + timedelta(minutes=5),
            error_code="provider_unavailable",
            error_category="transient",
            now=now,
        )
        assert await NotificationOutboxRepository.mark_failed(
            session,
            notification_id=second.id,
            claim_token=second_claim,
            error_code="recipient_rejected",
            error_category="permanent",
            failed_at=now,
        )

    async with factory() as session:
        retry = await session.get(NotificationOutbox, first.id)
        failed = await session.get(NotificationOutbox, second.id)
        assert retry is not None and retry.status == "retry_scheduled"
        assert retry.retry_count == 1
        assert failed is not None and failed.status == "failed"
        assert failed.terminal_failure

    abandoned = await enqueue_fixture(factory)
    claim_now = utc_now()
    async with factory() as session, session.begin():
        claimed = await NotificationOutboxRepository.claim_batch(
            session, worker_id="abandoned-worker", now=claim_now, limit=1
        )
        assert claimed[0].id == abandoned.id
    async with factory() as session, session.begin():
        assert (
            await NotificationOutboxRepository.release_abandoned_claims(
                session,
                claimed_before=claim_now + timedelta(seconds=1),
                release_at=claim_now + timedelta(seconds=1),
            )
            == 1
        )

    async with factory() as session, session.begin():
        cleanup_count = (
            await NotificationOutboxRepository.cleanup_completed_notifications(
                session,
                completed_before=now + timedelta(seconds=1),
                limit=10,
            )
        )
    assert cleanup_count == 1


@pytest.mark.asyncio
async def test_mark_sent_requires_the_active_claim_token(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    record = await enqueue_fixture(factory)
    now = utc_now()
    async with factory() as session, session.begin():
        claimed = await NotificationOutboxRepository.claim_batch(
            session, worker_id="worker-sent", now=now, limit=1
        )
        token = claimed[0].claim_token
        assert token is not None
        assert not await NotificationOutboxRepository.mark_sent(
            session,
            notification_id=record.id,
            claim_token=uuid4(),
            sent_at=now,
        )
        assert await NotificationOutboxRepository.mark_sent(
            session,
            notification_id=record.id,
            claim_token=token,
            sent_at=now,
        )

    async with factory() as session:
        sent = await session.get(NotificationOutbox, record.id)
        assert sent is not None
        assert sent.status == "sent"
        assert sent.sent_at == now
        assert sent.claim_token is None
