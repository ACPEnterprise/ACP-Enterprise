from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.errors import (
    SchedulingNotFoundError,
    SchedulingValidationError,
    SchedulingVersionConflictError,
)
from app.scheduling.models import (
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)
from app.scheduling.repository import SchedulingRepository, scheduling_repository
from app.scheduling.schemas import (
    BranchSchedulingExceptionInput,
    BranchSchedulingPolicyResponse,
    BranchSchedulingPolicyWrite,
    BranchWeeklyIntervalInput,
)


class BranchSchedulingAdministration:
    def __init__(
        self, repository: SchedulingRepository = scheduling_repository
    ) -> None:
        self._repository = repository

    async def read(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
    ) -> BranchSchedulingPolicyResponse:
        branch = await self._branch(session, context=context, branch_id=branch_id)
        calendar = await self._repository.get_branch_calendar(
            session, company_id=context.company.id, branch_id=branch_id
        )
        if calendar is None:
            return BranchSchedulingPolicyResponse(
                branch_id=branch.id,
                timezone=branch.timezone,
                status="NOT_CONFIGURED",
                readiness="SCHEDULING_SETUP_REQUIRED",
                blockers=(
                    "NO_ACTIVE_CALENDAR",
                    "NO_OPERATING_HOURS",
                    "CAPACITY_NOT_CONFIGURED",
                ),
                version=None,
                booking_horizon_days=None,
                minimum_notice_minutes=None,
                slot_interval_minutes=None,
                default_capacity_units=None,
                weekly_intervals=(),
                exceptions=(),
            )
        intervals = await self._repository.get_weekly_intervals(
            session,
            company_id=context.company.id,
            branch_id=branch_id,
            calendar_id=calendar.id,
        )
        exceptions = list(
            (
                await session.scalars(
                    select(BranchSchedulingException)
                    .where(BranchSchedulingException.calendar_id == calendar.id)
                    .order_by(
                        BranchSchedulingException.exception_date,
                        BranchSchedulingException.start_minute,
                        BranchSchedulingException.id,
                    )
                )
            ).all()
        )
        active = bool(intervals)
        return BranchSchedulingPolicyResponse(
            branch_id=branch.id,
            timezone=branch.timezone,
            status="ACTIVE" if active else "INACTIVE",
            readiness="SCHEDULING_READY" if active else "SCHEDULING_SETUP_REQUIRED",
            blockers=() if active else ("NO_ACTIVE_CALENDAR", "NO_OPERATING_HOURS"),
            version=calendar.concurrency_version,
            booking_horizon_days=calendar.booking_horizon_days,
            minimum_notice_minutes=calendar.minimum_notice_minutes,
            slot_interval_minutes=calendar.slot_interval_minutes,
            default_capacity_units=calendar.default_capacity_units,
            weekly_intervals=tuple(
                BranchWeeklyIntervalInput(
                    day_of_week=item.day_of_week,
                    start_minute=item.start_minute,
                    end_minute=item.end_minute,
                    capacity_units=item.capacity_units,
                )
                for item in intervals
            ),
            exceptions=tuple(
                BranchSchedulingExceptionInput(
                    exception_date=item.exception_date,
                    start_minute=item.start_minute,
                    end_minute=item.end_minute,
                    is_closed=item.is_closed,
                    capacity_units=item.capacity_units,
                    reason_code=item.reason_code,
                )
                for item in exceptions
            ),
        )

    async def configure(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
        policy: BranchSchedulingPolicyWrite,
    ) -> BranchSchedulingPolicyResponse:
        now = datetime.now(timezone.utc)
        async with session.begin():
            branch = await self._branch(session, context=context, branch_id=branch_id)
            try:
                ZoneInfo(policy.timezone)
            except ZoneInfoNotFoundError as error:
                raise SchedulingValidationError(
                    "Branch timezone is invalid."
                ) from error
            branch.timezone = policy.timezone
            calendar = await self._repository.get_branch_calendar(
                session,
                company_id=context.company.id,
                branch_id=branch_id,
                for_update=True,
            )
            prior_version = calendar.concurrency_version if calendar else None
            if calendar is None:
                if policy.expected_version is not None:
                    raise SchedulingVersionConflictError("Calendar does not exist.")
                calendar = BranchSchedulingCalendar(
                    company_id=context.company.id,
                    branch_id=branch_id,
                    booking_horizon_days=policy.booking_horizon_days,
                    minimum_notice_minutes=policy.minimum_notice_minutes,
                    slot_interval_minutes=policy.slot_interval_minutes,
                    default_capacity_units=policy.default_capacity_units,
                    concurrency_version=1,
                    created_by_user_id=context.user.id,
                    updated_by_user_id=context.user.id,
                    created_at=now,
                    updated_at=now,
                )
                await self._repository.create_branch_calendar(
                    session, calendar=calendar
                )
            else:
                if policy.expected_version != calendar.concurrency_version:
                    raise SchedulingVersionConflictError("Calendar version is stale.")
                calendar.booking_horizon_days = policy.booking_horizon_days
                calendar.minimum_notice_minutes = policy.minimum_notice_minutes
                calendar.slot_interval_minutes = policy.slot_interval_minutes
                calendar.default_capacity_units = policy.default_capacity_units
                calendar.concurrency_version += 1
                calendar.updated_by_user_id = context.user.id
                calendar.updated_at = now
                await session.execute(
                    delete(BranchSchedulingWeeklyInterval).where(
                        BranchSchedulingWeeklyInterval.calendar_id == calendar.id
                    )
                )
                await session.execute(
                    delete(BranchSchedulingException).where(
                        BranchSchedulingException.calendar_id == calendar.id
                    )
                )
            if policy.active:
                session.add_all(
                    [
                        BranchSchedulingWeeklyInterval(
                            calendar_id=calendar.id,
                            day_of_week=item.day_of_week,
                            start_minute=item.start_minute,
                            end_minute=item.end_minute,
                            capacity_units=item.capacity_units,
                            created_at=now,
                            updated_at=now,
                        )
                        for item in policy.weekly_intervals
                    ]
                )
            session.add_all(
                [
                    BranchSchedulingException(
                        calendar_id=calendar.id,
                        exception_date=item.exception_date,
                        start_minute=item.start_minute,
                        end_minute=item.end_minute,
                        is_closed=item.is_closed,
                        capacity_units=item.capacity_units,
                        reason_code=item.reason_code,
                        created_at=now,
                        updated_at=now,
                    )
                    for item in policy.exceptions
                ]
            )
            changed_fields = (
                "active",
                "timezone",
                "booking_horizon_days",
                "minimum_notice_minutes",
                "slot_interval_minutes",
                "default_capacity_units",
                "weekly_intervals",
                "exceptions",
            )
            audit_service.stage(
                session,
                AuditEntry(
                    action="branch_scheduling_policy.configure",
                    resource_type="branch_scheduling_calendar",
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=branch.id,
                    resource_id=calendar.id,
                    reason_code="OWNER_CONFIGURED",
                    details={
                        "prior_version": prior_version,
                        "new_version": calendar.concurrency_version,
                        "changed_fields": changed_fields,
                        "reason": policy.reason,
                    },
                ),
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.BRANCH_SCHEDULING_POLICY_CONFIGURED,
                    entity_type="branch_scheduling_calendar",
                    entity_id=calendar.id,
                    company_id=context.company.id,
                    branch_id=branch.id,
                    user_id=context.user.id,
                    payload={
                        "version": calendar.concurrency_version,
                        "active": policy.active,
                        "weekly_interval_count": len(policy.weekly_intervals)
                        if policy.active
                        else 0,
                        "exception_count": len(policy.exceptions),
                        "schema_version": 1,
                    },
                ),
            )
        return await self.read(session, context=context, branch_id=branch_id)

    @staticmethod
    async def _branch(
        session: AsyncSession, *, context: AuthorizationContext, branch_id: UUID
    ) -> Branch:
        if not context.can_access_branch(branch_id):
            raise SchedulingNotFoundError("Branch", branch_id)
        branch = await session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == context.company.id,
                Branch.archived_at.is_(None),
            )
        )
        if branch is None:
            raise SchedulingNotFoundError("Branch", branch_id)
        return branch


branch_scheduling_administration = BranchSchedulingAdministration()
