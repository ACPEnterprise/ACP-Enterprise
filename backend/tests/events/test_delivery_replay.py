from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.events import delivery_contracts
from app.events.delivery import BusinessEventDeliveryService, DeliveryConflict
from app.events.delivery_contracts import ConsumerDefinition, ConsumerMode
from app.events.models import (
    BusinessEvent,
    BusinessEventConsumerReceipt,
    BusinessEventDelivery,
    BusinessEventDeliveryEvidence,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType

NOW = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
COMPANY_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMPANY_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BRANCH_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa01")
REPLAY_SAFE = "test.replay_safe"
ORDERED = "test.ordered"


@pytest_asyncio.fixture
async def delivery_database(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    monkeypatch.setattr(
        delivery_contracts,
        "CONSUMER_REGISTRY",
        delivery_contracts.CONSUMER_REGISTRY
        + (
            ConsumerDefinition(
                REPLAY_SAFE,
                ConsumerMode.IDEMPOTENT_REPLAY_SAFE,
                frozenset({"1.0"}),
                "BANK.PLAT.005 synthetic consumer",
                frozenset({EventType.SYSTEM_STARTED.value}),
            ),
            ConsumerDefinition(
                ORDERED,
                ConsumerMode.IDEMPOTENT_ORDERED,
                frozenset({"1.0"}),
                "BANK.PLAT.005 synthetic ordered consumer",
            ),
        ),
    )
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO companies "
                "(id,name,code,status,timezone,created_at,updated_at) VALUES "
                "(:company,'Event Delivery Qualification','EVENTDELIVERY','active',"
                "'America/New_York',:now,:now) ON CONFLICT (id) DO NOTHING"
            ),
            {"company": COMPANY_A, "now": NOW},
        )
        await connection.execute(
            text(
                "INSERT INTO branches "
                "(id,company_id,name,code,status,timezone,is_primary,created_at,updated_at) "
                "VALUES (:branch,:company,'Event Delivery Qualification','EVENTDELIVERY',"
                "'active','America/New_York',false,:now,:now) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"branch": BRANCH_A, "company": COMPANY_A, "now": NOW},
        )
    await _truncate(engine)
    try:
        yield factory
    finally:
        await _truncate(engine)
        await engine.dispose()


async def _truncate(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE business_event_consumer_cursors, business_event_consumer_receipts, business_event_delivery_evidence, business_event_deliveries, business_events CASCADE"
            )
        )


async def _delivery(
    factory: async_sessionmaker[AsyncSession],
    *,
    consumer: str = REPLAY_SAFE,
    sequence: int | None = None,
    version: object = "1.0",
    company: UUID = COMPANY_A,
    branch: UUID | None = BRANCH_A,
    entity_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    async with factory() as session, session.begin():
        payload: dict[str, object] = {"schema_version": version}
        if sequence is not None:
            payload["aggregate_sequence"] = sequence
        event = BusinessEvent(
            event_type="test.changed",
            entity_type="test",
            entity_id=entity_id or uuid4(),
            company_id=company,
            branch_id=branch,
            payload=payload,
            correlation_id=uuid4(),
            occurred_at=NOW,
            created_at=NOW,
        )
        session.add(event)
        await session.flush()
        delivery = await BusinessEventDeliveryService.register(
            session, event=event, consumer_name=consumer, now=NOW
        )
        return event.id, delivery.id


async def _claim(
    factory: async_sessionmaker[AsyncSession], delivery_id: UUID, *, now: datetime = NOW
) -> UUID:
    async with factory() as session, session.begin():
        claimed = await BusinessEventDeliveryService.claim_batch(
            session,
            consumer_name=REPLAY_SAFE,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            worker_id="worker-a",
            now=now,
            claim_expires_at=now + timedelta(minutes=5),
            limit=10,
        )
        row = next(item for item in claimed if item.id == delivery_id)
        assert row.claim_token is not None
        return row.claim_token


@pytest.mark.asyncio
async def test_domain_transaction_atomically_stages_registered_delivery(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    async with delivery_database() as session, session.begin():
        event = BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.SYSTEM_STARTED,
                entity_type="system",
                company_id=COMPANY_A,
                branch_id=BRANCH_A,
                payload={"schema_version": "1.0"},
            ),
        )
        await session.flush()
        delivery = await session.scalar(
            select(BusinessEventDelivery).where(
                BusinessEventDelivery.event_id == event.id
            )
        )
        assert delivery is not None
        assert delivery.status == "pending"
        assert delivery.consumer_name == REPLAY_SAFE


@pytest.mark.asyncio
async def test_pending_delivery_is_durable_and_claim_is_concurrency_safe(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    _, delivery_id = await _delivery(delivery_database)
    async with delivery_database() as first, first.begin():
        claimed = await BusinessEventDeliveryService.claim_batch(
            first,
            consumer_name=REPLAY_SAFE,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            worker_id="worker-a",
            now=NOW,
            claim_expires_at=NOW + timedelta(minutes=5),
            limit=10,
        )
        assert [item.id for item in claimed] == [delivery_id]
        async with delivery_database() as second, second.begin():
            duplicate = await BusinessEventDeliveryService.claim_batch(
                second,
                consumer_name=REPLAY_SAFE,
                company_id=COMPANY_A,
                branch_id=BRANCH_A,
                worker_id="worker-b",
                now=NOW,
                claim_expires_at=NOW + timedelta(minutes=5),
                limit=10,
            )
            assert duplicate == ()


@pytest.mark.asyncio
async def test_transient_retry_preserves_event_and_does_not_duplicate_effect(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    event_id, delivery_id = await _delivery(delivery_database)
    token = await _claim(delivery_database, delivery_id)
    async with delivery_database() as session, session.begin():
        row = await BusinessEventDeliveryService.fail(
            session,
            delivery_id=delivery_id,
            claim_token=token,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            error_code="provider_unavailable",
            error_category="transient",
            retry_at=NOW + timedelta(minutes=10),
            max_attempts=3,
            now=NOW + timedelta(minutes=1),
        )
        assert row.status == "retryable"
        assert row.event_id == event_id
    retry_token = await _claim(
        delivery_database, delivery_id, now=NOW + timedelta(minutes=10)
    )
    digest = "a" * 64
    async with delivery_database() as session, session.begin():
        assert await BusinessEventDeliveryService.record_consumer_effect(
            session,
            delivery_id=delivery_id,
            claim_token=retry_token,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            outcome_digest=digest,
            now=NOW + timedelta(minutes=10),
        )
    async with delivery_database() as session, session.begin():
        row = await BusinessEventDeliveryService.acknowledge(
            session,
            delivery_id=delivery_id,
            claim_token=retry_token,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            now=NOW + timedelta(minutes=11),
        )
        assert row.status == "delivered"


@pytest.mark.asyncio
async def test_crash_after_effect_before_ack_recovers_idempotently(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    _, delivery_id = await _delivery(delivery_database)
    token = await _claim(delivery_database, delivery_id)
    async with delivery_database() as session, session.begin():
        assert await BusinessEventDeliveryService.record_consumer_effect(
            session,
            delivery_id=delivery_id,
            claim_token=token,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            outcome_digest="b" * 64,
            now=NOW,
        )
    recovered = await _claim(
        delivery_database, delivery_id, now=NOW + timedelta(minutes=6)
    )
    async with delivery_database() as session, session.begin():
        assert not await BusinessEventDeliveryService.record_consumer_effect(
            session,
            delivery_id=delivery_id,
            claim_token=recovered,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            outcome_digest="b" * 64,
            now=NOW + timedelta(minutes=6),
        )
        await BusinessEventDeliveryService.acknowledge(
            session,
            delivery_id=delivery_id,
            claim_token=recovered,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            now=NOW + timedelta(minutes=6),
        )
    async with delivery_database() as session:
        assert (
            await session.scalar(
                select(BusinessEventConsumerReceipt).where(
                    BusinessEventConsumerReceipt.event_id.is_not(None)
                )
            )
            is not None
        )
        outcomes = tuple(
            (
                await session.scalars(
                    select(BusinessEventDeliveryEvidence.outcome).order_by(
                        BusinessEventDeliveryEvidence.evidence_sequence
                    )
                )
            ).all()
        )
        assert outcomes == (
            "claimed",
            "recovered",
            "claimed",
            "idempotent",
            "delivered",
        )


@pytest.mark.asyncio
async def test_terminal_failure_and_authorized_replay_preserve_original_event(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    event_id, delivery_id = await _delivery(delivery_database)
    token = await _claim(delivery_database, delivery_id)
    async with delivery_database() as session, session.begin():
        failed = await BusinessEventDeliveryService.fail(
            session,
            delivery_id=delivery_id,
            claim_token=token,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            error_code="unsupported_destination",
            error_category="terminal",
            retry_at=None,
            max_attempts=3,
            now=NOW,
        )
        assert failed.status == "terminal"
    async with delivery_database() as session, session.begin():
        actor_id = uuid4()
        request_id = uuid4()
        with pytest.raises(DeliveryConflict, match="authority"):
            await BusinessEventDeliveryService.request_replay(
                session,
                delivery_id=delivery_id,
                company_id=COMPANY_A,
                branch_id=BRANCH_A,
                actor_user_id=actor_id,
                request_id=request_id,
                authorized=False,
                now=NOW,
            )
        replay = await BusinessEventDeliveryService.request_replay(
            session,
            delivery_id=delivery_id,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            actor_user_id=actor_id,
            request_id=request_id,
            authorized=True,
            now=NOW,
        )
        assert replay.event_id == event_id
        assert replay.status == "pending"
        assert replay.replay_count == 1
        identical = await BusinessEventDeliveryService.request_replay(
            session,
            delivery_id=delivery_id,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            actor_user_id=actor_id,
            request_id=request_id,
            authorized=True,
            now=NOW,
        )
        assert identical.id == replay.id
        assert identical.replay_count == 1


@pytest.mark.asyncio
async def test_unknown_version_and_cross_tenant_operations_fail_closed(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(DeliveryConflict, match="Unsupported"):
        await _delivery(delivery_database, version="99.0")
    _, delivery_id = await _delivery(delivery_database)
    async with delivery_database() as session, session.begin():
        assert (
            await BusinessEventDeliveryService.claim_batch(
                session,
                consumer_name=REPLAY_SAFE,
                company_id=COMPANY_B,
                branch_id=BRANCH_A,
                worker_id="wrong",
                now=NOW,
                claim_expires_at=NOW + timedelta(minutes=1),
                limit=1,
            )
            == ()
        )
    token = await _claim(delivery_database, delivery_id)
    async with delivery_database() as session, session.begin():
        with pytest.raises(DeliveryConflict, match="scope"):
            await BusinessEventDeliveryService.record_consumer_effect(
                session,
                delivery_id=delivery_id,
                claim_token=token,
                company_id=COMPANY_B,
                branch_id=BRANCH_A,
                outcome_digest="c" * 64,
                now=NOW,
            )


@pytest.mark.asyncio
async def test_ordered_consumer_rejects_stale_application(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    entity_id = uuid4()
    _, newer_id = await _delivery(
        delivery_database, consumer=ORDERED, sequence=2, entity_id=entity_id
    )
    _, stale_id = await _delivery(
        delivery_database, consumer=ORDERED, sequence=1, entity_id=entity_id
    )
    async with delivery_database() as session, session.begin():
        claimed = await BusinessEventDeliveryService.claim_batch(
            session,
            consumer_name=ORDERED,
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            worker_id="ordered",
            now=NOW,
            claim_expires_at=NOW + timedelta(minutes=5),
            limit=10,
        )
        tokens = {item.id: item.claim_token for item in claimed}
    async with delivery_database() as session, session.begin():
        assert tokens[newer_id] is not None
        await BusinessEventDeliveryService.record_consumer_effect(
            session,
            delivery_id=newer_id,
            claim_token=tokens[newer_id],
            company_id=COMPANY_A,
            branch_id=BRANCH_A,
            outcome_digest="d" * 64,
            now=NOW,
        )
    async with delivery_database() as session, session.begin():
        assert tokens[stale_id] is not None
        with pytest.raises(DeliveryConflict, match="stale"):
            await BusinessEventDeliveryService.record_consumer_effect(
                session,
                delivery_id=stale_id,
                claim_token=tokens[stale_id],
                company_id=COMPANY_A,
                branch_id=BRANCH_A,
                outcome_digest="e" * 64,
                now=NOW,
            )


@pytest.mark.asyncio
async def test_delivery_evidence_and_receipts_are_database_immutable(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    _, delivery_id = await _delivery(delivery_database)
    await _claim(delivery_database, delivery_id)
    async with delivery_database() as session, session.begin():
        evidence_id = await session.scalar(select(BusinessEventDeliveryEvidence.id))
        with pytest.raises(DBAPIError):
            await session.execute(
                update(BusinessEventDeliveryEvidence)
                .where(BusinessEventDeliveryEvidence.id == evidence_id)
                .values(outcome="terminal")
            )


@pytest.mark.asyncio
async def test_delivery_scope_parity_and_registered_receipt_are_database_enforced(
    delivery_database: async_sessionmaker[AsyncSession],
) -> None:
    event_id, delivery_id = await _delivery(delivery_database)

    with pytest.raises(DBAPIError):
        async with delivery_database() as session, session.begin():
            session.add(
                BusinessEventDelivery(
                    event_id=event_id,
                    consumer_name=ORDERED,
                    event_version="1.0",
                    company_id=None,
                    branch_id=None,
                    status="pending",
                    attempt_count=0,
                    replay_count=0,
                    next_attempt_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await session.flush()

    with pytest.raises(DBAPIError):
        async with delivery_database() as session, session.begin():
            session.add(
                BusinessEventDeliveryEvidence(
                    delivery_id=delivery_id,
                    event_id=event_id,
                    consumer_name=REPLAY_SAFE,
                    company_id=None,
                    branch_id=None,
                    evidence_sequence=1,
                    attempt_number=0,
                    outcome="claimed",
                    recorded_at=NOW,
                )
            )
            await session.flush()

    with pytest.raises(DBAPIError):
        async with delivery_database() as session, session.begin():
            session.add(
                BusinessEventConsumerReceipt(
                    event_id=event_id,
                    consumer_name=ORDERED,
                    company_id=COMPANY_A,
                    branch_id=BRANCH_A,
                    outcome_digest="a" * 64,
                    created_at=NOW,
                )
            )
            await session.flush()
