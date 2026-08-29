from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .errors import EmployeeIdentityNotReady
from .repository import EmployeeDayRepository, employee_day_repository
from .schemas import (
    EmployeeDayAssignment,
    EmployeeDayResponse,
    EmployeeServiceLocation,
)


class EmployeeDayService:
    def __init__(self, repository: EmployeeDayRepository = employee_day_repository):
        self.repository = repository

    async def day(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        business_date: date | None = None,
        observed_at: datetime | None = None,
    ) -> EmployeeDayResponse:
        employee = await self.repository.employee_for_membership(
            session,
            company_id=context.company.id,
            membership_id=context.membership.id,
        )
        if employee is None:
            raise EmployeeIdentityNotReady(
                "Authenticated membership is not linked to an active Employee."
            )
        timezone_name = (
            context.active_branch.timezone
            if context.active_branch is not None
            else context.company.timezone
        )
        zone = ZoneInfo(timezone_name)
        now = observed_at or datetime.now(timezone.utc)
        resolved_date = business_date or now.astimezone(zone).date()
        start_at = datetime.combine(resolved_date, time.min, zone).astimezone(
            timezone.utc
        )
        end_at = datetime.combine(
            resolved_date + timedelta(days=1), time.min, zone
        ).astimezone(timezone.utc)
        records = await self.repository.assignments_for_day(
            session,
            company_id=context.company.id,
            employee_id=employee.id,
            authorized_branch_ids=context.authorized_branch_ids,
            start_at=start_at,
            end_at=end_at,
        )
        return EmployeeDayResponse(
            business_date=resolved_date,
            timezone=timezone_name,
            assignments=tuple(
                EmployeeDayAssignment(
                    appointment_id=value.appointment_id,
                    appointment_number=value.appointment_number,
                    appointment_status=value.appointment_status,
                    job_id=value.job_id,
                    job_number=value.job_number,
                    job_status=value.job_status,
                    service_category=value.service_category,
                    window_start_at=value.window_start_at,
                    window_end_at=value.window_end_at,
                    assignment_role=value.assignment_role,
                    assignment_status=value.assignment_status,
                    designation=None,
                    customer_display_name=value.customer_display_name,
                    service_location=EmployeeServiceLocation(
                        label=value.location_nickname or value.address_line_1,
                        address_line_1=value.address_line_1,
                        address_line_2=value.address_line_2,
                        city=value.city,
                        state=value.state,
                        postal_code=value.postal_code,
                        country=value.country,
                    ),
                )
                for value in records
            ),
        )


employee_day_service = EmployeeDayService()
