from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.delivery_contracts import delivery_consumers, event_version
from app.events.models import BusinessEvent, BusinessEventDelivery
from app.events.schemas import BusinessEventCreate
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.security.safe_output import validate_no_sensitive_fields


class BusinessEventService:
    @staticmethod
    def stage(
        session: AsyncSession,
        event_data: BusinessEventCreate,
    ) -> BusinessEvent:
        """Add an event to the current transaction without committing it."""
        validate_no_sensitive_fields(
            event_data.payload,
            boundary="Business Event payload",
            include_personal=False,
        )
        now = event_data.occurred_at or datetime.now(timezone.utc)
        event = BusinessEvent(
            id=uuid4(),
            event_type=event_data.event_type.value,
            entity_type=event_data.entity_type,
            entity_id=event_data.entity_id,
            company_id=event_data.company_id,
            branch_id=event_data.branch_id,
            user_id=event_data.user_id,
            payload=event_data.payload,
            correlation_id=event_data.correlation_id or uuid4(),
            occurred_at=now,
        )
        session.add(event)
        consumers = delivery_consumers(event_data.event_type.value)
        version = event_version(event_data.payload) if consumers else "1.0"
        for consumer in consumers:
            if version not in consumer.supported_versions:
                raise ValueError(
                    "Business Event version is unsupported by its consumer."
                )
            session.add(
                BusinessEventDelivery(
                    event_id=event.id,
                    consumer_name=consumer.name,
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
            )
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
        context: AuthorizationContext,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BusinessEvent]:
        statement = (
            select(BusinessEvent)
            .where(BusinessEvent.company_id == context.company.id)
            .order_by(
                BusinessEvent.occurred_at.desc(),
                BusinessEvent.created_at.desc(),
                BusinessEvent.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        if not context.membership.has_all_branch_access:
            statement = statement.where(
                or_(
                    BusinessEvent.branch_id.is_(None),
                    BusinessEvent.branch_id.in_(context.authorized_branch_ids),
                )
            )

        result = await session.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def latest_events(
        session: AsyncSession,
        context: AuthorizationContext,
        limit: int = 10,
    ) -> list[BusinessEvent]:
        return await BusinessEventService.list_events(
            session=session,
            context=context,
            limit=limit,
            offset=0,
        )
