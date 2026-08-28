"""Read model for self-service and manager Workday Time APIs."""

from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PunchKind, WorkdayAuthorizationError, WorkdayTimeError
from .models import PayPeriod, WorkdayPunchEvent, WorkdayTimeEntryRevision
from .repository import TimekeepingRepository, timekeeping_repository
from .schemas import PayPeriodView, PunchState, TimecardView, TimeEntryView


class WorkdayTimeQueryService:
    def __init__(
        self, repository: TimekeepingRepository = timekeeping_repository
    ) -> None:
        self._repository = repository

    async def self_employee(
        self, session: AsyncSession, context: AuthorizationContext
    ):
        employee = await self._repository.employee_for_membership(
            session,
            company_id=context.company.id,
            membership_id=context.membership.id,
        )
        if employee is None:
            raise WorkdayAuthorizationError(
                "authenticated membership is not linked to an active Employee"
            )
        return employee

    async def state(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        observed_at: datetime | None = None,
    ) -> PunchState:
        now = observed_at or datetime.now(timezone.utc)
        latest = await self._repository.latest_punch(
            session, company_id=context.company.id, employee_id=employee_id
        )
        clock_in = await self._repository.latest_clock_in(
            session, company_id=context.company.id, employee_id=employee_id
        )
        return self._punch_state(latest, clock_in, now)

    async def own_timecard(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> TimecardView:
        employee = await self.self_employee(session, context)
        timezone_name = (
            context.active_branch.timezone
            if context.active_branch is not None
            else context.company.timezone
        )
        today = datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
        period = await self._repository.pay_period_for_date(
            session, company_id=context.company.id, work_date=today
        )
        start_date, end_date = (
            (period.period_start, period.period_end)
            if period is not None
            else (today, today)
        )
        revisions = await self._repository.current_employee_revisions(
            session,
            company_id=context.company.id,
            employee_id=employee.id,
            start_date=start_date,
            end_date=end_date,
        )
        return TimecardView(
            employee_id=employee.id,
            punch_state=await self.state(
                session, context=context, employee_id=employee.id
            ),
            pay_period=self.pay_period_view(period) if period is not None else None,
            entries=tuple(self.entry_view(value) for value in revisions),
        )

    @staticmethod
    def entry_view(value: WorkdayTimeEntryRevision) -> TimeEntryView:
        return TimeEntryView(
            entry_id=value.entry_id,
            revision_id=value.id,
            revision_number=value.revision_number,
            work_date=value.work_date,
            timezone=value.timezone,
            provenance=value.provenance,
            start_at=value.start_at,
            end_at=value.end_at,
            approved_duration_minutes=value.approved_duration_minutes,
            state=value.state,
            supersedes_revision_id=value.supersedes_revision_id,
            correction_reason=value.correction_reason,
            approved_at=value.approved_at,
        )

    @staticmethod
    def pay_period_view(value: PayPeriod) -> PayPeriodView:
        return PayPeriodView(
            id=value.id,
            period_start=value.period_start,
            period_end=value.period_end,
            processing_date=value.processing_date,
            payday=value.payday,
            timezone=value.timezone,
            schedule_definition_id=value.schedule_definition_id,
            schedule_version=value.schedule_version,
        )

    @staticmethod
    def _punch_state(
        latest: WorkdayPunchEvent | None,
        clock_in: WorkdayPunchEvent | None,
        observed_at: datetime,
    ) -> PunchState:
        if latest is None or latest.kind == PunchKind.CLOCK_OUT.value:
            return PunchState(
                state="not_clocked_in",
                last_action=PunchKind(latest.kind) if latest is not None else None,
                occurred_at=latest.occurred_at if latest is not None else None,
                server_observed_at=observed_at,
                elapsed_seconds=None,
            )
        if clock_in is None or observed_at < clock_in.occurred_at:
            raise WorkdayTimeError("active punch state lacks a valid clock-in")
        return PunchState(
            state=(
                "on_break"
                if latest.kind == PunchKind.BREAK_START.value
                else "clocked_in"
            ),
            last_action=PunchKind(latest.kind),
            occurred_at=latest.occurred_at,
            server_observed_at=observed_at,
            elapsed_seconds=int((observed_at - clock_in.occurred_at).total_seconds()),
        )


workday_time_queries = WorkdayTimeQueryService()
