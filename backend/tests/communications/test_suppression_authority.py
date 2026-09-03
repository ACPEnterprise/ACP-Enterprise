from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.communications.suppression import (
    CommunicationRecipientControl,
    RecipientControlDecision,
    SuppressionScope,
    SuppressionSource,
    recipient_suppression_repository,
)
from app.communications.types import CommunicationChannel, CommunicationPurpose
from app.core.config import settings
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

NOW = datetime(2026, 9, 2, 18, tzinfo=timezone.utc)


def decision(
    *,
    company_id,
    scope: SuppressionScope,
    source: SuppressionSource,
    active: bool,
    occurred_at: datetime,
    event_key: str,
) -> RecipientControlDecision:
    return RecipientControlDecision(
        company_id=company_id,
        channel=CommunicationChannel.SMS,
        destination_digest="a" * 64,
        scope=scope,
        source=source,
        active=active,
        provider_event_key=event_key,
        source_evidence_digest="b" * 64,
        occurred_at=occurred_at,
        recorded_at=NOW,
    )


@pytest.mark.asyncio
async def test_suppression_is_replay_safe_and_purpose_specific() -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company_id = uuid4()
    try:
        marketing = decision(
            company_id=company_id,
            scope=SuppressionScope.MARKETING_OUTREACH,
            source=SuppressionSource.MARKETING_OPT_OUT,
            active=True,
            occurred_at=NOW,
            event_key="marketing-stop-1",
        )
        async with factory() as session, session.begin():
            first, created = await recipient_suppression_repository.record(
                session, marketing
            )
            replay, replay_created = await recipient_suppression_repository.record(
                session, marketing
            )
            assert created and not replay_created and first.id == replay.id
        async with factory() as session:
            assert await recipient_suppression_repository.is_suppressed(
                session,
                company_id=company_id,
                channel=CommunicationChannel.SMS,
                destination_digest_value="a" * 64,
                purpose=CommunicationPurpose.MARKETING_OUTREACH,
            )
            assert not await recipient_suppression_repository.is_suppressed(
                session,
                company_id=company_id,
                channel=CommunicationChannel.SMS,
                destination_digest_value="a" * 64,
                purpose=CommunicationPurpose.OPERATIONAL,
            )
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(CommunicationRecipientControl).where(
                    CommunicationRecipientControl.company_id == company_id
                )
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_latest_control_releases_only_the_same_suppression_authority() -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company_id = uuid4()
    try:
        async with factory() as session, session.begin():
            await recipient_suppression_repository.record(
                session,
                decision(
                    company_id=company_id,
                    scope=SuppressionScope.ALL,
                    source=SuppressionSource.SMS_STOP,
                    active=True,
                    occurred_at=NOW,
                    event_key="stop-1",
                ),
            )
            await recipient_suppression_repository.record(
                session,
                decision(
                    company_id=company_id,
                    scope=SuppressionScope.ALL,
                    source=SuppressionSource.SMS_STOP,
                    active=False,
                    occurred_at=NOW + timedelta(minutes=1),
                    event_key="start-1",
                ),
            )
        async with factory() as session:
            assert not await recipient_suppression_repository.is_suppressed(
                session,
                company_id=company_id,
                channel=CommunicationChannel.SMS,
                destination_digest_value="a" * 64,
                purpose=CommunicationPurpose.OPERATIONAL,
            )
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(CommunicationRecipientControl).where(
                    CommunicationRecipientControl.company_id == company_id
                )
            )
        await engine.dispose()
