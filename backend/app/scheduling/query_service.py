from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.errors import SchedulingNotFoundError, SchedulingValidationError
from app.scheduling.query import (
    MAX_CALENDAR_RANGE,
    AppointmentQuery,
    AppointmentQueryRecord,
    AppointmentQueryResult,
)
from app.scheduling.repository import SchedulingRepository, scheduling_repository


class SchedulingQueryService:
    """Own query validation and authorization orchestration without SQL."""

    def __init__(
        self, repository: SchedulingRepository = scheduling_repository
    ) -> None:
        self._repository = repository

    async def get_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: AppointmentQuery,
    ) -> AppointmentQueryRecord:
        self._validate_scope(context, query)
        if query.appointment_id is None:
            raise SchedulingValidationError("Appointment identifier is required.")
        record = await self._repository.get_appointment_query_record(
            session, query=query
        )
        if record is None:
            raise SchedulingNotFoundError("Appointment", query.appointment_id)
        return record

    async def search_appointments(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: AppointmentQuery,
    ) -> AppointmentQueryResult:
        self._validate_scope(context, query)
        if query.start_at is None or query.end_at is None:
            raise SchedulingValidationError("Query range is required.")
        if query.start_at.tzinfo is None or query.end_at.tzinfo is None:
            raise SchedulingValidationError("Query range must be timezone-aware.")
        if query.end_at <= query.start_at:
            raise SchedulingValidationError("Query range end must follow start.")
        if query.end_at - query.start_at > MAX_CALENDAR_RANGE:
            raise SchedulingValidationError("Query range exceeds the maximum.")
        items, total = await self._repository.search_appointment_query_records(
            session, query=query
        )
        return AppointmentQueryResult(
            items=items,
            total_count=total,
            page=query.page,
            page_size=query.page_size,
        )

    @staticmethod
    def _validate_scope(context: AuthorizationContext, query: AppointmentQuery) -> None:
        if query.company_id != context.company.id:
            raise SchedulingValidationError("Query Company is invalid.")
        if query.authorized_branch_ids != context.authorized_branch_ids:
            raise SchedulingValidationError("Query Branch scope is invalid.")
        if query.branch_id is not None and not context.can_access_branch(
            query.branch_id
        ):
            raise SchedulingNotFoundError("Branch", query.branch_id)
        if query.page < 1 or not 1 <= query.page_size <= 200:
            raise SchedulingValidationError("Query pagination is invalid.")


scheduling_query_service = SchedulingQueryService()
