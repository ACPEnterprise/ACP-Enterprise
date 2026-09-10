"""Read model for self-service and manager Workday Time APIs."""

from datetime import datetime, timezone
from itertools import pairwise
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PunchKind, WorkdayAuthorizationError, WorkdayTimeError
from .models import PayPeriod, WorkdayPunchEvent, WorkdayTimeEntryRevision
from .repository import TimekeepingRepository, timekeeping_repository
from .schemas import (
    AdminTimecardReview,
    AdminTimecardReviewItem,
    PayPeriodView,
    PunchState,
    TimecardView,
    TimeEntryView,
)


class WorkdayTimeQueryService:
    def __init__(
        self, repository: TimekeepingRepository = timekeeping_repository
    ) -> None:
        self._repository = repository

    async def self_employee(self, session: AsyncSession, context: AuthorizationContext):
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

    async def admin_review(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> AdminTimecardReview:
        """Return a read-only, Branch-scoped current-period exception queue."""
        timezone_name = (
            context.active_branch.timezone
            if context.active_branch is not None
            else context.company.timezone
        )
        today = datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
        period = await self._repository.pay_period_for_date(
            session, company_id=context.company.id, work_date=today
        )
        if period is None:
            return AdminTimecardReview(pay_period=None, items=())
        branch_ids = context.authorized_branch_ids
        employees = tuple(
            (
                await session.scalars(
                    select(Employee)
                    .where(
                        Employee.company_id == context.company.id,
                        Employee.status == "active",
                    )
                    .order_by(Employee.display_name, Employee.id)
                )
            ).all()
        )
        employees = tuple(
            item
            for item in employees
            if item.home_branch_id is None or item.home_branch_id in branch_ids
        )
        employee_ids = tuple(item.id for item in employees)
        revisions = (
            tuple(
                (
                    await session.scalars(
                        select(WorkdayTimeEntryRevision)
                        .where(
                            WorkdayTimeEntryRevision.company_id == context.company.id,
                            WorkdayTimeEntryRevision.employee_id.in_(employee_ids),
                            WorkdayTimeEntryRevision.work_date >= period.period_start,
                            WorkdayTimeEntryRevision.work_date <= period.period_end,
                        )
                        .order_by(
                            WorkdayTimeEntryRevision.entry_id,
                            WorkdayTimeEntryRevision.revision_number.desc(),
                        )
                    )
                ).all()
            )
            if employee_ids
            else ()
        )
        current: dict[UUID, WorkdayTimeEntryRevision] = {}
        for revision in revisions:
            current.setdefault(revision.entry_id, revision)
        by_employee: dict[UUID, list[WorkdayTimeEntryRevision]] = {}
        for revision in current.values():
            if revision.branch_id is None or revision.branch_id in branch_ids:
                by_employee.setdefault(revision.employee_id, []).append(revision)
        items: list[AdminTimecardReviewItem] = []
        for employee in employees:
            entries = sorted(
                by_employee.get(employee.id, []),
                key=lambda item: (item.start_at or item.created_at, item.id),
            )
            exceptions: set[str] = set()
            if not entries:
                exceptions.add("no_time")
            if any(item.state not in {"submitted", "approved"} for item in entries):
                exceptions.add("unsubmitted")
            if any(
                item.state == "corrected" or item.correction_reason is not None
                for item in entries
            ):
                exceptions.add("corrected")
            timed = [item for item in entries if item.start_at and item.end_at]
            if any(
                left.end_at is not None
                and right.start_at is not None
                and left.end_at > right.start_at
                for left, right in pairwise(timed)
            ):
                exceptions.add("overlap")
            total = sum(
                item.approved_duration_minutes
                if item.approved_duration_minutes is not None
                else int((item.end_at - item.start_at).total_seconds() // 60)
                if item.start_at is not None and item.end_at is not None
                else 0
                for item in entries
            )
            items.append(
                AdminTimecardReviewItem(
                    employee_id=employee.id,
                    employee_number=employee.employee_number,
                    display_name=employee.display_name,
                    home_branch_id=employee.home_branch_id,
                    entry_count=len(entries),
                    total_minutes=total,
                    exception_codes=tuple(sorted(exceptions)),  # type: ignore[arg-type]
                    entries=tuple(self.entry_view(value) for value in entries),
                )
            )
        return AdminTimecardReview(
            pay_period=self.pay_period_view(period), items=tuple(items)
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
            correction_kind=value.correction_kind,
            reviewed_by_user_id=value.responsible_user_id,
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
