"""Read model for self-service and manager Workday Time APIs."""

from collections import defaultdict
from datetime import date, datetime, timezone
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
    AdminEmployeeTimecard,
    AdminTimecardDay,
    AdminTimecardInterval,
    AdminTimecardOperations,
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

    async def admin_pay_periods(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        limit: int,
    ) -> tuple[PayPeriodView, ...]:
        """Return a bounded Company-owned period index for office navigation."""
        periods = (
            await session.scalars(
                select(PayPeriod)
                .where(PayPeriod.company_id == context.company.id)
                .order_by(PayPeriod.period_end.desc(), PayPeriod.id)
                .limit(limit)
            )
        ).all()
        return tuple(self.pay_period_view(period) for period in periods)

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
        branch_ids = (
            frozenset({context.active_branch.id})
            if context.active_branch is not None
            else context.authorized_branch_ids
        )
        employee_scope = Employee.home_branch_id.in_(branch_ids)
        if context.active_branch is None:
            employee_scope = employee_scope | Employee.home_branch_id.is_(None)
        employees = tuple(
            (
                await session.scalars(
                    select(Employee)
                    .where(
                        Employee.company_id == context.company.id,
                        Employee.status == "active",
                        employee_scope,
                    )
                    .order_by(Employee.display_name, Employee.id)
                )
            ).all()
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
            if revision.branch_id in branch_ids or (
                context.active_branch is None and revision.branch_id is None
            ):
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

    async def admin_operations(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        pay_period_id: UUID,
        observed_at: datetime | None = None,
    ) -> AdminTimecardOperations:
        """Detailed, read-only period evidence without inventing Job attribution."""
        period = await self._repository.pay_period_by_id(
            session, company_id=context.company.id, pay_period_id=pay_period_id
        )
        if period is None:
            raise WorkdayTimeError("pay period does not exist in this Company")
        now = observed_at or datetime.now(timezone.utc)
        branch_ids = (
            frozenset({context.active_branch.id})
            if context.active_branch is not None
            else context.authorized_branch_ids
        )
        employee_scope = Employee.home_branch_id.in_(branch_ids)
        if context.active_branch is None:
            employee_scope = employee_scope | Employee.home_branch_id.is_(None)
        employees = tuple(
            (
                await session.scalars(
                    select(Employee)
                    .where(
                        Employee.company_id == context.company.id,
                        Employee.status == "active",
                        employee_scope,
                    )
                    .order_by(Employee.display_name, Employee.id)
                )
            ).all()
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
        by_employee: dict[UUID, list[WorkdayTimeEntryRevision]] = defaultdict(list)
        for revision in current.values():
            if revision.branch_id in branch_ids or (
                context.active_branch is None and revision.branch_id is None
            ):
                by_employee[revision.employee_id].append(revision)
        punch_states = await self._admin_punch_states(
            session,
            company_id=context.company.id,
            employee_ids=employee_ids,
            observed_at=now,
        )
        rows: list[AdminEmployeeTimecard] = []
        for employee in employees:
            values = sorted(
                by_employee[employee.id],
                key=lambda item: (item.work_date, item.start_at or item.created_at, item.id),
            )
            punch_state, active_clock_in = punch_states[employee.id]
            local_today = now.astimezone(ZoneInfo(period.timezone)).date()
            missing_clock_out = bool(
                punch_state.state != "not_clocked_in"
                and active_clock_in is not None
                and active_clock_in.astimezone(ZoneInfo(period.timezone)).date()
                < local_today
            )
            days = self._operation_days(values)
            exceptions = {
                code
                for day in days
                for code, present in (
                    ("overlap", day.has_overlap),
                    ("corrected", day.has_correction),
                    ("unreviewed", day.review_state == "NEEDS_REVIEW"),
                )
                if present
            }
            if punch_state.state != "not_clocked_in":
                exceptions.add("open_clock")
            if missing_clock_out:
                exceptions.add("missing_clock_out")
            total = sum(day.total_supported_minutes for day in days)
            accepted = sum(
                interval.supported_minutes
                for day in days
                for interval in day.intervals
                if interval.review_state == "ACCEPTED"
            )
            rows.append(
                AdminEmployeeTimecard(
                    employee_id=employee.id,
                    employee_number=employee.employee_number,
                    display_name=employee.display_name,
                    home_branch_id=employee.home_branch_id,
                    punch_state=punch_state,
                    active_open_clock=punch_state.state != "not_clocked_in",
                    missing_clock_out=missing_clock_out,
                    days=days,
                    total_supported_minutes=total,
                    accepted_minutes=accepted,
                    exception_codes=tuple(sorted(exceptions)),
                    review_state="NEEDS_REVIEW" if exceptions else "ACCEPTED",
                )
            )
        return AdminTimecardOperations(
            contract_version="WORKFORCE.TIMECARD.OPERATIONS.v1",
            pay_period=self.pay_period_view(period),
            employees=tuple(rows),
            job_attribution_readiness="PARTIAL",
            limitations=(
                "Timekeeping currently proves Employee paid-time intervals, not Job attribution.",
                "Unclassified supported time is not silently assigned to a Job or labeled non-Job time.",
                "Regular and overtime candidates remain Payroll policy outputs.",
            ),
        )

    async def _admin_punch_states(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_ids: tuple[UUID, ...],
        observed_at: datetime,
    ) -> dict[UUID, tuple[PunchState, datetime | None]]:
        if not employee_ids:
            return {}
        latest = tuple(
            (
                await session.scalars(
                    select(WorkdayPunchEvent)
                    .where(
                        WorkdayPunchEvent.company_id == company_id,
                        WorkdayPunchEvent.employee_id.in_(employee_ids),
                    )
                    .distinct(WorkdayPunchEvent.employee_id)
                    .order_by(
                        WorkdayPunchEvent.employee_id,
                        WorkdayPunchEvent.occurred_at.desc(),
                        WorkdayPunchEvent.id.desc(),
                    )
                )
            ).all()
        )
        clock_ins = tuple(
            (
                await session.scalars(
                    select(WorkdayPunchEvent)
                    .where(
                        WorkdayPunchEvent.company_id == company_id,
                        WorkdayPunchEvent.employee_id.in_(employee_ids),
                        WorkdayPunchEvent.kind == PunchKind.CLOCK_IN.value,
                    )
                    .distinct(WorkdayPunchEvent.employee_id)
                    .order_by(
                        WorkdayPunchEvent.employee_id,
                        WorkdayPunchEvent.occurred_at.desc(),
                        WorkdayPunchEvent.id.desc(),
                    )
                )
            ).all()
        )
        latest_by_employee = {item.employee_id: item for item in latest}
        clock_in_by_employee = {item.employee_id: item for item in clock_ins}
        return {
            employee_id: (
                self._punch_state(
                    latest_by_employee.get(employee_id),
                    clock_in_by_employee.get(employee_id),
                    observed_at,
                ),
                (
                    clock_in_by_employee[employee_id].occurred_at
                    if employee_id in clock_in_by_employee
                    and latest_by_employee.get(employee_id) is not None
                    and latest_by_employee[employee_id].kind != PunchKind.CLOCK_OUT.value
                    else None
                ),
            )
            for employee_id in employee_ids
        }

    @classmethod
    def _operation_days(
        cls, values: list[WorkdayTimeEntryRevision]
    ) -> tuple[AdminTimecardDay, ...]:
        grouped: dict[date, list[WorkdayTimeEntryRevision]] = defaultdict(list)
        for value in values:
            grouped[value.work_date].append(value)
        days: list[AdminTimecardDay] = []
        for work_date, entries in sorted(grouped.items()):
            entries.sort(key=lambda item: (item.start_at or item.created_at, item.id))
            overlap_ids: set[UUID] = set()
            timed = [item for item in entries if item.start_at and item.end_at]
            for left, right in pairwise(timed):
                if left.end_at is not None and right.start_at is not None and left.end_at > right.start_at:
                    overlap_ids.update((left.id, right.id))
            intervals: list[AdminTimecardInterval] = []
            for item in entries:
                minutes = cls._minutes(item)
                accepted = item.state == "approved" or item.approved_at is not None
                intervals.append(
                    AdminTimecardInterval(
                        entry_id=item.entry_id,
                        revision_id=item.id,
                        revision_number=item.revision_number,
                        work_date=item.work_date,
                        start_at=item.start_at,
                        end_at=item.end_at,
                        supported_minutes=minutes,
                        attribution_state="UNCLASSIFIED",
                        provenance=item.provenance,
                        entry_state=item.state,
                        corrected=item.revision_number > 1 or item.correction_reason is not None,
                        overlap=item.id in overlap_ids,
                        review_state="ACCEPTED" if accepted else "NEEDS_REVIEW",
                        audit_digest=item.evidence_digest,
                    )
                )
            total = sum(item.supported_minutes for item in intervals)
            days.append(
                AdminTimecardDay(
                    work_date=work_date,
                    intervals=tuple(intervals),
                    total_supported_minutes=total,
                    job_minutes=None,
                    non_job_supported_minutes=None,
                    unclassified_minutes=total,
                    has_overlap=bool(overlap_ids),
                    has_correction=any(item.corrected for item in intervals),
                    review_state=(
                        "ACCEPTED"
                        if all(item.review_state == "ACCEPTED" for item in intervals)
                        and not overlap_ids
                        else "NEEDS_REVIEW"
                    ),
                )
            )
        return tuple(days)

    @staticmethod
    def _minutes(value: WorkdayTimeEntryRevision) -> int:
        if value.approved_duration_minutes is not None:
            return value.approved_duration_minutes
        if value.start_at is not None and value.end_at is not None:
            return int((value.end_at - value.start_at).total_seconds() // 60)
        return 0

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
