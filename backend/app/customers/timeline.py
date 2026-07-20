from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.errors import CustomerNotFoundError
from app.customers.repository import CustomerRepository
from app.customers.schemas import (
    CustomerTimelineEntry,
    TimelineActor,
    TimelineEntity,
)
from app.events.models import BusinessEvent
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User


SAFE_METADATA_FIELDS = frozenset(
    {
        "changed_fields",
        "customer_id",
        "customer_number",
        "customer_type",
        "is_preferred",
        "previous_status",
        "status",
    }
)


@dataclass(frozen=True)
class TimelinePage:
    items: list[CustomerTimelineEntry]
    total_count: int


class CustomerTimelineService:
    async def get_timeline(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        page: int,
        page_size: int,
    ) -> TimelinePage:
        customer = await CustomerRepository.get(
            session,
            company_id=context.company.id,
            customer_id=customer_id,
        )
        if customer is None:
            raise CustomerNotFoundError(customer_id)

        customer_reference = str(customer_id)
        event_filter = or_(
            (BusinessEvent.entity_type == "customer")
            & (BusinessEvent.entity_id == customer_id),
            BusinessEvent.payload["customer_id"].astext == customer_reference,
        )
        total = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.company_id == context.company.id,
                event_filter,
            )
        )
        rows = (
            await session.execute(
                select(BusinessEvent, User)
                .outerjoin(User, User.id == BusinessEvent.user_id)
                .where(
                    BusinessEvent.company_id == context.company.id,
                    event_filter,
                )
                .order_by(BusinessEvent.occurred_at.desc(), BusinessEvent.id.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
        return TimelinePage(
            items=[
                self._entry(event, actor, customer_id=customer_id)
                for event, actor in rows
            ],
            total_count=int(total or 0),
        )

    def _entry(
        self,
        event: BusinessEvent,
        actor: User | None,
        *,
        customer_id: UUID,
    ) -> CustomerTimelineEntry:
        if event.company_id is None:
            raise ValueError("Customer timeline events require Company ownership")
        return CustomerTimelineEntry(
            id=event.id,
            timestamp=event.occurred_at,
            event_type=event.event_type,
            actor=(
                TimelineActor(id=actor.id, display_name=actor.display_name)
                if actor is not None
                else None
            ),
            entity=TimelineEntity(type=event.entity_type, id=event.entity_id),
            summary=self._summary(event),
            metadata=self._safe_metadata(event.payload),
            branch_id=event.branch_id,
            company_id=event.company_id,
            customer_id=customer_id,
            correlation_id=event.correlation_id,
        )

    @staticmethod
    def _safe_metadata(payload: dict[str, object]) -> dict[str, object]:
        return {
            key: value
            for key, value in payload.items()
            if key in SAFE_METADATA_FIELDS
            and isinstance(value, (str, int, float, bool, list, type(None)))
        }

    @staticmethod
    def _summary(event: BusinessEvent) -> str:
        if event.event_type == "customer.created":
            return "Customer created"
        if event.event_type == "customer.updated":
            return "Customer updated"
        if event.event_type == "customer.status_changed":
            status = (
                str(event.payload.get("status", "updated")).replace("_", " ").title()
            )
            return f"Status changed to {status}"
        if event.event_type == "contact.created":
            return "Contact added"
        if event.event_type == "contact.updated":
            changed = event.payload.get("changed_fields", [])
            if isinstance(changed, list) and "is_preferred" in changed:
                return "Preferred Contact updated"
            return "Contact updated"
        if event.event_type == "contact.deactivated":
            return "Contact deactivated"
        if event.event_type == "service_location.created":
            return "Service Location added"
        if event.event_type == "service_location.updated":
            return "Service Location updated"
        if event.event_type == "service_location.deactivated":
            return "Service Location deactivated"
        if event.event_type.startswith("authentication."):
            return "Customer access authentication event"
        return event.event_type.replace(".", " ").replace("_", " ").title()


customer_timeline_service = CustomerTimelineService()
