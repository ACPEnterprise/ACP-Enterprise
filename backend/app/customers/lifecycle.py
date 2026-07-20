from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.errors import CustomerNotFoundError
from app.customers.models import Customer
from app.customers.repository import CustomerRepository
from app.customers.schemas import CustomerLifecycleResponse
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import AuthorizationContext


class CustomerArchiveGuard(Protocol):
    """Extension boundary for operational modules that can block archival."""

    async def validate_archive(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> None: ...


class CustomerLifecycleService:
    def __init__(self, archive_guards: Sequence[CustomerArchiveGuard] = ()) -> None:
        self._archive_guards = tuple(archive_guards)

    async def archive(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> CustomerLifecycleResponse:
        async with session.begin():
            customer = await self._locked_customer(session, context, customer_id)
            if customer.archived_at is None:
                for guard in self._archive_guards:
                    await guard.validate_archive(
                        session,
                        context=context,
                        customer_id=customer_id,
                    )
                now = datetime.now(timezone.utc)
                CustomerRepository.set_archive_state(
                    customer, archived_at=now, updated_at=now
                )
                self._stage_event(
                    session,
                    context=context,
                    customer_id=customer.id,
                    event_type=EventType.CUSTOMER_ARCHIVED,
                )
        return self._response(customer)

    async def restore(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> CustomerLifecycleResponse:
        async with session.begin():
            customer = await self._locked_customer(session, context, customer_id)
            if customer.archived_at is not None:
                now = datetime.now(timezone.utc)
                CustomerRepository.set_archive_state(
                    customer, archived_at=None, updated_at=now
                )
                self._stage_event(
                    session,
                    context=context,
                    customer_id=customer.id,
                    event_type=EventType.CUSTOMER_RESTORED,
                )
        return self._response(customer)

    @staticmethod
    async def _locked_customer(
        session: AsyncSession,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> Customer:
        customer = await CustomerRepository.get_for_lifecycle(
            session,
            company_id=context.company.id,
            customer_id=customer_id,
        )
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        return customer

    @staticmethod
    def _stage_event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        event_type: EventType,
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="customer",
                entity_id=customer_id,
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                user_id=context.user.id,
                payload={"customer_id": str(customer_id)},
            ),
        )

    @staticmethod
    def _response(customer: Customer) -> CustomerLifecycleResponse:
        return CustomerLifecycleResponse(
            customer_id=customer.id,
            company_id=customer.company_id,
            archived=customer.archived_at is not None,
            archived_at=customer.archived_at,
            updated_at=customer.updated_at,
        )


customer_lifecycle_service = CustomerLifecycleService()
