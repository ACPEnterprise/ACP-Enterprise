from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate


class BusinessEventService:
    @staticmethod
    def stage(
        session: AsyncSession,
        event_data: BusinessEventCreate,
    ) -> BusinessEvent:
        """Add an event to the current transaction without committing it."""
        event = BusinessEvent(
            event_type=event_data.event_type.value,
            entity_type=event_data.entity_type,
            entity_id=event_data.entity_id,
            company_id=event_data.company_id,
            branch_id=event_data.branch_id,
            user_id=event_data.user_id,
            payload=event_data.payload,
            correlation_id=event_data.correlation_id or uuid4(),
            occurred_at=event_data.occurred_at or datetime.now(timezone.utc),
        )
        session.add(event)
        return event

    @staticmethod
    async def publish(
        session: AsyncSession,
        event_data: BusinessEventCreate,
    ) -> BusinessEvent:
        event = BusinessEventService.stage(session, event_data)

        try:
            await session.commit()
            await session.refresh(event)
        except Exception:
            await session.rollback()
            raise

        return event

    @staticmethod
    async def list_events(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BusinessEvent]:
        statement = (
            select(BusinessEvent)
            .order_by(
                BusinessEvent.occurred_at.desc(),
                BusinessEvent.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await session.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def latest_events(
        session: AsyncSession,
        limit: int = 10,
    ) -> list[BusinessEvent]:
        return await BusinessEventService.list_events(
            session=session,
            limit=limit,
            offset=0,
        )
