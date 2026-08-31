import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.events.models import BusinessEvent  # noqa: F401
from app.platform.branch.models import Branch  # noqa: F401
from app.platform.company.membership_models import Membership  # noqa: F401
from app.platform.company.models import Company  # noqa: F401
from app.platform.notifications.models import (
    NotificationDeliveryEvidence,
    NotificationOutbox,
)
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.permissions.models import (  # noqa: F401
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential  # noqa: F401


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def persist_company(session: AsyncSession, company_id: UUID) -> None:
    now = utc_now()
    await session.execute(
        text(
            "INSERT INTO companies "
            "(id, name, code, status, timezone, created_at, updated_at) "
            "VALUES (:id, :name, :code, 'active', 'UTC', :now, :now) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": company_id,
            "name": f"Notification test {company_id}",
            "code": f"N{company_id.hex.upper()}",
            "now": now,
        },
    )


async def persist_scope(
    session: AsyncSession, company_id: UUID, branch_id: UUID
) -> None:
    now = utc_now()
    await persist_company(session, company_id)
    await session.execute(
        text(
            "INSERT INTO branches "
            "(id, company_id, name, code, status, timezone, is_primary, "
            "created_at, updated_at) "
            "VALUES (:id, :company_id, :name, :code, 'active', 'UTC', false, "
            ":now, :now)"
        ),
        {
            "id": branch_id,
            "company_id": company_id,
            "name": f"Notification branch {branch_id}",
            "code": f"N{branch_id.hex.upper()}",
            "now": now,
        },
    )


async def persist_user(session: AsyncSession, user_id: UUID) -> None:
    now = utc_now()
    await session.execute(
        text(
            "INSERT INTO users "
            "(id, normalized_email, first_name, last_name, display_name, status, "
            "authorization_version, created_at, updated_at) "
            "VALUES (:id, :email, 'Notification', 'Actor', 'Notification Actor', "
            "'active', 1, :now, :now)"
        ),
        {"id": user_id, "email": f"{user_id}@example.invalid", "now": now},
    )


async def persist_membership(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> None:
    now = utc_now()
    await persist_user(session, user_id)
    await session.execute(
        text(
            "INSERT INTO memberships "
            "(id, user_id, company_id, status, has_all_branch_access, "
            "created_at, updated_at) "
            "VALUES (:id, :user_id, :company_id, 'active', true, :now, :now)"
        ),
        {
            "id": uuid4(),
            "user_id": user_id,
            "company_id": company_id,
            "now": now,
        },
    )


async def persist_event(
    session: AsyncSession,
    event_id: UUID,
    *,
    company_id: UUID | None,
    branch_id: UUID | None,
) -> None:
    now = utc_now()
    await session.execute(
        text(
            "INSERT INTO business_events "
            "(id, event_type, entity_type, company_id, branch_id, payload, "
            "correlation_id, occurred_at, created_at) "
            "VALUES (:id, 'test.notification_source', 'test', :company_id, "
            ":branch_id, '{}'::jsonb, :correlation_id, :now, :now)"
        ),
        {
            "id": event_id,
            "company_id": company_id,
            "branch_id": branch_id,
            "correlation_id": uuid4(),
            "now": now,
        },
    )


@pytest_asyncio.fixture
async def outbox_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(
            text("TRUNCATE notification_delivery_evidence, notification_outbox CASCADE")
        )
    try:
        yield engine, factory
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "TRUNCATE notification_delivery_evidence, notification_outbox CASCADE"
                )
            )
        await engine.dispose()


async def enqueue_fixture(
    factory: async_sessionmaker[AsyncSession],
    *,
    key: str | None = None,
    scheduled_at: datetime | None = None,
    company_id: UUID | None = None,
) -> NotificationOutbox:
    now = utc_now()
    scoped_company_id = company_id or uuid4()
    async with factory() as session, session.begin():
        await persist_company(session, scoped_company_id)
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
            company_id=scoped_company_id,
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
    company_id = uuid4()
    async with factory() as session, session.begin():
        await persist_company(session, company_id)
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
            company_id=company_id,
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
            company_id=company_id,
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


@pytest.mark.asyncio
async def test_contradictory_intent_replay_fails_closed(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    now = utc_now()
    key = f"intent:{uuid4()}"
    correlation_id = uuid4()
    company_id = uuid4()
    async with factory() as session, session.begin():
        await persist_company(session, company_id)
        await NotificationOutboxRepository.enqueue(
            session,
            notification_type="customer.notice",
            template_identifier="notice-v1",
            recipient="customer@example.com",
            payload={"subject_id": "one"},
            correlation_id=correlation_id,
            idempotency_key=key,
            scheduled_at=now,
            now=now,
            company_id=company_id,
        )
        with pytest.raises(ValueError, match="contradictory intent"):
            await NotificationOutboxRepository.enqueue(
                session,
                notification_type="customer.notice",
                template_identifier="notice-v1",
                recipient="customer@example.com",
                payload={"subject_id": "two"},
                correlation_id=correlation_id,
                idempotency_key=key,
                scheduled_at=now,
                now=now,
                company_id=company_id,
            )


@pytest.mark.asyncio
async def test_indeterminate_provider_result_blocks_unsafe_resend(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    record = await enqueue_fixture(factory)
    now = utc_now()
    async with factory() as session, session.begin():
        claimed = await NotificationOutboxRepository.claim_batch(
            session, worker_id="provider-worker", now=now, limit=1
        )
        token = claimed[0].claim_token
        assert token is not None
        assert await NotificationOutboxRepository.record_provider_submission(
            session,
            notification_id=record.id,
            claim_token=token,
            submitted_at=now,
            provider_reference="synthetic-provider-reference",
        )
        assert not await NotificationOutboxRepository.schedule_retry(
            session,
            notification_id=record.id,
            claim_token=token,
            scheduled_at=now + timedelta(minutes=1),
            error_code="response_lost",
            error_category="indeterminate",
            now=now,
        )
        assert await NotificationOutboxRepository.mark_ambiguous(
            session,
            notification_id=record.id,
            claim_token=token,
            error_code="response_lost",
            at=now,
        )

    async with factory() as session:
        ambiguous = await session.get(NotificationOutbox, record.id)
        evidence = list(
            (
                await session.scalars(
                    select(NotificationDeliveryEvidence)
                    .where(NotificationDeliveryEvidence.outbox_id == record.id)
                    .order_by(NotificationDeliveryEvidence.sequence)
                )
            ).all()
        )
        assert ambiguous is not None and ambiguous.status == "ambiguous"
        assert [entry.outcome for entry in evidence] == [
            "claimed",
            "submitted",
            "ambiguous",
        ]


@pytest.mark.asyncio
async def test_terminal_cleanup_archives_instead_of_deleting(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    record = await enqueue_fixture(factory)
    now = utc_now()
    async with factory() as session, session.begin():
        claimed = await NotificationOutboxRepository.claim_batch(
            session, worker_id="archive-worker", now=now, limit=1
        )
        token = claimed[0].claim_token
        assert token is not None
        assert await NotificationOutboxRepository.mark_sent(
            session,
            notification_id=record.id,
            claim_token=token,
            sent_at=now,
        )
    async with factory() as session, session.begin():
        assert (
            await NotificationOutboxRepository.cleanup_completed_notifications(
                session,
                completed_before=now + timedelta(seconds=1),
                limit=1,
            )
            == 1
        )
    async with factory() as session:
        archived = await session.get(NotificationOutbox, record.id)
        assert archived is not None
        assert archived.archived_at == now + timedelta(seconds=1)


@pytest.mark.asyncio
async def test_company_and_branch_scoped_acquisition_does_not_cross_tenants(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    now = utc_now()
    company_a, company_b, branch_a, branch_b = (uuid4() for _ in range(4))
    async with factory() as session, session.begin():
        await persist_scope(session, company_a, branch_a)
        await persist_scope(session, company_b, branch_b)
        for company_id, branch_id in ((company_a, branch_a), (company_b, branch_b)):
            await NotificationOutboxRepository.enqueue(
                session,
                notification_type="customer.notice",
                template_identifier="notice-v1",
                recipient="synthetic@example.com",
                payload={"company_id": str(company_id)},
                correlation_id=uuid4(),
                idempotency_key=f"tenant:{company_id}",
                scheduled_at=now,
                now=now,
                company_id=company_id,
                branch_id=branch_id,
            )

    async with factory() as session, session.begin():
        claimed = await NotificationOutboxRepository.claim_batch(
            session,
            worker_id="tenant-worker",
            now=now,
            limit=10,
            company_id=company_a,
            branch_id=branch_a,
        )
        assert len(claimed) == 1
        assert claimed[0].company_id == company_a
        assert claimed[0].branch_id == branch_a


@pytest.mark.asyncio
async def test_authorized_suppression_is_terminal_and_auditable(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    company_id = uuid4()
    record = await enqueue_fixture(factory, company_id=company_id)
    now = utc_now()
    actor = uuid4()
    reason_digest = "a" * 64
    async with factory() as session, session.begin():
        await persist_membership(session, actor, company_id)
        assert not await NotificationOutboxRepository.suppress_or_cancel(
            session,
            notification_id=record.id,
            company_id=company_id,
            target="suppressed",
            actor_user_id=actor,
            reason_digest=reason_digest,
            authorized=False,
            now=now,
        )
        assert await NotificationOutboxRepository.suppress_or_cancel(
            session,
            notification_id=record.id,
            company_id=company_id,
            target="suppressed",
            actor_user_id=actor,
            reason_digest=reason_digest,
            authorized=True,
            now=now,
        )
        assert not await NotificationOutboxRepository.claim_batch(
            session, worker_id="provider-worker", now=now, limit=10
        )

    async with factory() as session:
        evidence = await session.scalar(
            select(NotificationDeliveryEvidence).where(
                NotificationDeliveryEvidence.outbox_id == record.id
            )
        )
        assert evidence is not None
        assert evidence.outcome == "suppressed"
        assert evidence.actor_user_id == actor
        assert evidence.reason_digest == reason_digest
        evidence_id = evidence.id

    async with factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                update(NotificationDeliveryEvidence)
                .where(NotificationDeliveryEvidence.id == evidence_id)
                .values(outcome="cancelled")
            )
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                delete(NotificationDeliveryEvidence).where(
                    NotificationDeliveryEvidence.id == evidence_id
                )
            )


@pytest.mark.asyncio
async def test_delivery_evidence_rejects_missing_or_foreign_company_actor(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    company_id, foreign_company_id = uuid4(), uuid4()
    record = await enqueue_fixture(factory, company_id=company_id)
    foreign_actor = uuid4()
    async with factory() as session, session.begin():
        await persist_company(session, foreign_company_id)
        await persist_membership(session, foreign_actor, foreign_company_id)
        for actor_user_id in (uuid4(), foreign_actor):
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    session.add(
                        NotificationDeliveryEvidence(
                            outbox_id=record.id,
                            sequence=1,
                            outcome="suppressed",
                            company_id=company_id,
                            actor_user_id=actor_user_id,
                            reason_digest="a" * 64,
                            recorded_at=utc_now(),
                        )
                    )
                    await session.flush()


@pytest.mark.asyncio
async def test_same_key_is_isolated_by_company_and_replays_per_tenant(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    now = utc_now()
    company_a, company_b = uuid4(), uuid4()
    key = f"shared-provider-identity:{uuid4()}"

    async with factory() as session, session.begin():
        await persist_company(session, company_a)
        await persist_company(session, company_b)
        first_a, created_a = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="customer.notice",
            template_identifier="notice-v1",
            recipient="tenant-a@example.invalid",
            payload={"safe_subject_id": "a"},
            correlation_id=uuid4(),
            idempotency_key=key,
            scheduled_at=now,
            now=now,
            company_id=company_a,
        )
        first_b, created_b = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="customer.notice",
            template_identifier="notice-v1",
            recipient="tenant-b@example.invalid",
            payload={"safe_subject_id": "b"},
            correlation_id=uuid4(),
            idempotency_key=key,
            scheduled_at=now,
            now=now,
            company_id=company_b,
        )
        replay_a, replay_created_a = await NotificationOutboxRepository.enqueue(
            session,
            notification_type=first_a.notification_type,
            template_identifier=first_a.template_identifier,
            recipient=first_a.recipient,
            payload=first_a.payload,
            correlation_id=first_a.correlation_id,
            idempotency_key=key,
            scheduled_at=first_a.scheduled_at,
            now=now,
            company_id=company_a,
        )
        replay_b, replay_created_b = await NotificationOutboxRepository.enqueue(
            session,
            notification_type=first_b.notification_type,
            template_identifier=first_b.template_identifier,
            recipient=first_b.recipient,
            payload=first_b.payload,
            correlation_id=first_b.correlation_id,
            idempotency_key=key,
            scheduled_at=first_b.scheduled_at,
            now=now,
            company_id=company_b,
        )

    assert created_a and created_b
    assert first_a.id != first_b.id
    assert not replay_created_a and replay_a.id == first_a.id
    assert not replay_created_b and replay_b.id == first_b.id


@pytest.mark.asyncio
async def test_cross_company_mutation_is_rejected_for_shared_key(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    company_a, company_b = uuid4(), uuid4()
    record = await enqueue_fixture(
        factory, key=f"shared:{uuid4()}", company_id=company_a
    )
    now = utc_now()
    async with factory() as session, session.begin():
        assert not await NotificationOutboxRepository.suppress_or_cancel(
            session,
            notification_id=record.id,
            company_id=company_b,
            target="suppressed",
            actor_user_id=uuid4(),
            reason_digest="b" * 64,
            authorized=True,
            now=now,
        )
    async with factory() as session:
        unchanged = await session.get(NotificationOutbox, record.id)
        assert unchanged is not None and unchanged.status == "pending"


@pytest.mark.asyncio
async def test_concurrent_same_key_creation_is_independent_across_companies(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    now = utc_now()
    key = f"concurrent-shared:{uuid4()}"

    async def create(company_id: UUID) -> NotificationOutbox:
        async with factory() as session, session.begin():
            record, created = await NotificationOutboxRepository.enqueue(
                session,
                notification_type="customer.notice",
                template_identifier="notice-v1",
                recipient=f"tenant-{company_id}@example.invalid",
                payload={"safe_company_id": str(company_id)},
                correlation_id=uuid4(),
                idempotency_key=key,
                scheduled_at=now,
                now=now,
                company_id=company_id,
            )
            assert created
            return record

    company_a, company_b = uuid4(), uuid4()
    async with factory() as session, session.begin():
        await persist_company(session, company_a)
        await persist_company(session, company_b)
    first, second = await asyncio.gather(create(company_a), create(company_b))
    assert first.id != second.id
    assert {first.company_id, second.company_id} == {company_a, company_b}


@pytest.mark.asyncio
async def test_concurrent_same_company_replay_creates_one_intent(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    now = utc_now()
    company_id = uuid4()
    key = f"concurrent-same-tenant:{uuid4()}"
    correlation_id = uuid4()
    payload: dict[str, object] = {"safe_subject_id": str(uuid4())}

    async with factory() as session, session.begin():
        await persist_company(session, company_id)

    async def create() -> tuple[NotificationOutbox, bool]:
        async with factory() as session, session.begin():
            return await NotificationOutboxRepository.enqueue(
                session,
                notification_type="customer.notice",
                template_identifier="notice-v1",
                recipient="same-tenant@example.invalid",
                payload=payload,
                correlation_id=correlation_id,
                idempotency_key=key,
                scheduled_at=now,
                now=now,
                company_id=company_id,
            )

    first, second = await asyncio.gather(create(), create())
    assert first[0].id == second[0].id
    assert sorted((first[1], second[1])) == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parent_company", "parent_branch", "evidence_company", "evidence_branch"),
    [
        (uuid4(), uuid4(), uuid4(), uuid4()),
        (uuid4(), uuid4(), None, None),
        (None, None, uuid4(), uuid4()),
    ],
)
async def test_delivery_evidence_rejects_forged_or_null_bypassed_scope(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    parent_company: UUID | None,
    parent_branch: UUID | None,
    evidence_company: UUID | None,
    evidence_branch: UUID | None,
) -> None:
    _, factory = outbox_database
    now = utc_now()
    async with factory() as session, session.begin():
        if parent_company is not None and parent_branch is not None:
            await persist_scope(session, parent_company, parent_branch)
        parent, _ = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="customer.notice",
            template_identifier="notice-v1",
            recipient="scope-test@example.invalid",
            payload={"safe_subject_id": str(uuid4())},
            correlation_id=uuid4(),
            idempotency_key=f"scope:{uuid4()}",
            scheduled_at=now,
            now=now,
            company_id=parent_company,
            branch_id=parent_branch,
        )
        session.add(
            NotificationDeliveryEvidence(
                outbox_id=parent.id,
                sequence=1,
                outcome="claimed",
                company_id=evidence_company,
                branch_id=evidence_branch,
                recorded_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_outbox_rejects_branch_without_company_or_from_another_company(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    company_a, company_b, branch_b = uuid4(), uuid4(), uuid4()
    async with factory() as session, session.begin():
        await persist_company(session, company_a)
        await persist_scope(session, company_b, branch_b)
        for company_id in (None, company_a):
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await NotificationOutboxRepository.enqueue(
                        session,
                        notification_type="customer.notice",
                        template_identifier="notice-v1",
                        recipient="scope-test@example.invalid",
                        payload={"safe_subject_id": str(uuid4())},
                        correlation_id=uuid4(),
                        idempotency_key=f"forged-scope:{uuid4()}",
                        scheduled_at=utc_now(),
                        now=utc_now(),
                        company_id=company_id,
                        branch_id=branch_b,
                    )


@pytest.mark.asyncio
async def test_outbox_rejects_forged_company_actor_and_source_event_scope(
    outbox_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = outbox_database
    company_a, company_b = uuid4(), uuid4()
    branch_a, branch_b = uuid4(), uuid4()
    actor_id, event_b = uuid4(), uuid4()
    now = utc_now()
    async with factory() as session, session.begin():
        await persist_scope(session, company_a, branch_a)
        await persist_scope(session, company_b, branch_b)
        await persist_user(session, actor_id)
        await persist_event(
            session, event_b, company_id=company_b, branch_id=branch_b
        )

        invalid_scopes = (
            {"company_id": uuid4()},
            {"company_id": company_a, "actor_user_id": uuid4()},
            {
                "company_id": company_a,
                "branch_id": branch_a,
                "source_event_id": event_b,
            },
        )
        for index, scope in enumerate(invalid_scopes):
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await NotificationOutboxRepository.enqueue(
                        session,
                        notification_type="customer.notice",
                        template_identifier="notice-v1",
                        recipient="authority-test@example.invalid",
                        payload={"safe_subject_id": str(uuid4())},
                        correlation_id=uuid4(),
                        idempotency_key=f"forged-authority:{index}:{uuid4()}",
                        scheduled_at=now,
                        now=now,
                        **scope,
                    )

        accepted, created = await NotificationOutboxRepository.enqueue(
            session,
            notification_type="customer.notice",
            template_identifier="notice-v1",
            recipient="authority-test@example.invalid",
            payload={"safe_subject_id": str(uuid4())},
            correlation_id=uuid4(),
            idempotency_key=f"exact-authority:{uuid4()}",
            scheduled_at=now,
            now=now,
            company_id=company_b,
            branch_id=branch_b,
            actor_user_id=actor_id,
            source_event_id=event_b,
        )
        assert created
        assert accepted.source_event_id == event_b
