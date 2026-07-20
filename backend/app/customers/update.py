from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.detail import CustomerDetailService, customer_detail_service
from app.customers.errors import CustomerNotFoundError, CustomerStatusTransitionError
from app.customers.normalization import normalize_search_text
from app.customers.repository import CustomerRepository
from app.customers.schemas import (
    CustomerDetailResponse,
    CustomerStatus,
    CustomerUpdateRequest,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import AuthorizationContext


ALLOWED_STATUS_TRANSITIONS: dict[CustomerStatus, frozenset[CustomerStatus]] = {
    CustomerStatus.PROSPECT: frozenset(
        {CustomerStatus.ACTIVE, CustomerStatus.INACTIVE}
    ),
    CustomerStatus.ACTIVE: frozenset({CustomerStatus.INACTIVE}),
    CustomerStatus.INACTIVE: frozenset({CustomerStatus.ACTIVE}),
}


class CustomerUpdateService:
    def __init__(self, detail_service: CustomerDetailService) -> None:
        self._detail_service = detail_service

    async def update(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        data: CustomerUpdateRequest,
    ) -> CustomerDetailResponse:
        requested = {
            key: value.value if hasattr(value, "value") else value
            for key, value in data.model_dump(exclude_unset=True).items()
        }
        async with session.begin():
            customer = await CustomerRepository.get(
                session,
                company_id=context.company.id,
                customer_id=customer_id,
                for_update=True,
            )
            if customer is None:
                raise CustomerNotFoundError(customer_id)

            previous_status = customer.status
            requested_status = requested.get("status")
            if isinstance(requested_status, str):
                self._validate_status_transition(previous_status, requested_status)

            if "display_name" in requested:
                requested["normalized_name"] = normalize_search_text(
                    str(requested["display_name"])
                )
            changed_fields = CustomerRepository.apply_updates(customer, requested)
            business_fields = sorted(
                field
                for field in changed_fields
                if field not in {"normalized_name", "updated_at"}
            )
            if business_fields:
                CustomerRepository.apply_updates(
                    customer, {"updated_at": datetime.now(timezone.utc)}
                )
                self._stage_event(
                    session,
                    context=context,
                    event_type=EventType.CUSTOMER_UPDATED,
                    customer_id=customer.id,
                    payload={"changed_fields": business_fields},
                )
                if "status" in business_fields:
                    self._stage_event(
                        session,
                        context=context,
                        event_type=EventType.CUSTOMER_STATUS_CHANGED,
                        customer_id=customer.id,
                        payload={
                            "previous_status": previous_status,
                            "status": customer.status,
                        },
                    )

        return await self._detail_service.get_detail(
            session, context=context, customer_id=customer_id
        )

    @staticmethod
    def _validate_status_transition(current: str, requested: str) -> None:
        current_status = CustomerStatus(current)
        requested_status = CustomerStatus(requested)
        if current_status == requested_status:
            return
        if requested_status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
            raise CustomerStatusTransitionError(current, requested)

    @staticmethod
    def _stage_event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        customer_id: UUID,
        payload: dict[str, object],
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
                payload=payload,
            ),
        )


customer_update_service = CustomerUpdateService(customer_detail_service)
