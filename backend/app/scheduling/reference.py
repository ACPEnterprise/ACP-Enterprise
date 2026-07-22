from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.scheduling.repository import SchedulingRepository, scheduling_repository
from app.scheduling.types import AppointmentReference


class SchedulingReferenceService:
    """Expose narrow immutable Appointment facts to other bounded contexts."""

    def __init__(
        self, repository: SchedulingRepository = scheduling_repository
    ) -> None:
        self._repository = repository

    async def get_appointment_reference(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        appointment_id: UUID,
        for_update: bool = False,
    ) -> AppointmentReference | None:
        return await self._repository.get_appointment_reference(
            session,
            company_id=company_id,
            appointment_id=appointment_id,
            for_update=for_update,
        )


scheduling_reference_service = SchedulingReferenceService()
