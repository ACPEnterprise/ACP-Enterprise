"""Company-scoped persistence queries for Workday Time."""

from datetime import date
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PayPeriod, WorkdayPunchEvent, WorkdayTimeEntryRevision


class TimekeepingRepository:
    async def employee_for_membership(
        self, session: AsyncSession, *, company_id: UUID, membership_id: UUID
    ):
        from app.platform.employees.models import Employee

        return await session.scalar(
            select(Employee).where(
                Employee.company_id == company_id,
                Employee.membership_id == membership_id,
                Employee.archived_at.is_(None),
            )
        )

    async def employee_exists(
        self, session: AsyncSession, *, company_id: UUID, employee_id: UUID
    ) -> bool:
        from app.platform.employees.models import Employee

        return bool(
            await session.scalar(
                select(
                    exists().where(
                        Employee.company_id == company_id,
                        Employee.id == employee_id,
                        Employee.archived_at.is_(None),
                    )
                )
            )
        )

    async def latest_punch(
        self, session: AsyncSession, *, company_id: UUID, employee_id: UUID
    ) -> WorkdayPunchEvent | None:
        return await session.scalar(
            select(WorkdayPunchEvent)
            .where(
                WorkdayPunchEvent.company_id == company_id,
                WorkdayPunchEvent.employee_id == employee_id,
            )
            .order_by(WorkdayPunchEvent.occurred_at.desc(), WorkdayPunchEvent.id.desc())
            .limit(1)
        )

    async def punch_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        recorded_by_user_id: UUID,
        idempotency_key: str,
    ) -> WorkdayPunchEvent | None:
        return await session.scalar(
            select(WorkdayPunchEvent).where(
                WorkdayPunchEvent.company_id == company_id,
                WorkdayPunchEvent.recorded_by_user_id == recorded_by_user_id,
                WorkdayPunchEvent.idempotency_key == idempotency_key,
            )
        )

    async def revision_for_punch(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        punch_id: UUID,
    ) -> WorkdayTimeEntryRevision | None:
        return await session.scalar(
            select(WorkdayTimeEntryRevision)
            .where(
                WorkdayTimeEntryRevision.company_id == company_id,
                WorkdayTimeEntryRevision.punch_event_ids.contains([str(punch_id)]),
            )
            .order_by(WorkdayTimeEntryRevision.revision_number.desc())
            .limit(1)
        )

    async def manual_revision_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        responsible_user_id: UUID,
        idempotency_key: str,
    ) -> WorkdayTimeEntryRevision | None:
        origin = await session.scalar(
            select(WorkdayTimeEntryRevision).where(
                WorkdayTimeEntryRevision.company_id == company_id,
                WorkdayTimeEntryRevision.responsible_user_id == responsible_user_id,
                WorkdayTimeEntryRevision.origin_idempotency_key == idempotency_key,
                WorkdayTimeEntryRevision.revision_number == 1,
            )
        )
        if origin is None:
            return None
        return await session.scalar(
            select(WorkdayTimeEntryRevision)
            .where(
                WorkdayTimeEntryRevision.company_id == company_id,
                WorkdayTimeEntryRevision.entry_id == origin.entry_id,
            )
            .order_by(WorkdayTimeEntryRevision.revision_number.desc())
            .limit(1)
        )

    async def latest_clock_in(
        self, session: AsyncSession, *, company_id: UUID, employee_id: UUID
    ) -> WorkdayPunchEvent | None:
        return await session.scalar(
            select(WorkdayPunchEvent)
            .where(
                WorkdayPunchEvent.company_id == company_id,
                WorkdayPunchEvent.employee_id == employee_id,
                WorkdayPunchEvent.kind == "clock_in",
            )
            .order_by(WorkdayPunchEvent.occurred_at.desc(), WorkdayPunchEvent.id.desc())
            .limit(1)
        )

    async def latest_revision(
        self, session: AsyncSession, *, company_id: UUID, revision_id: UUID
    ) -> WorkdayTimeEntryRevision | None:
        base = await session.scalar(
            select(WorkdayTimeEntryRevision).where(
                WorkdayTimeEntryRevision.company_id == company_id,
                WorkdayTimeEntryRevision.id == revision_id,
            )
        )
        if base is None:
            return None
        return await session.scalar(
            select(WorkdayTimeEntryRevision)
            .where(
                WorkdayTimeEntryRevision.company_id == company_id,
                WorkdayTimeEntryRevision.entry_id == base.entry_id,
            )
            .order_by(WorkdayTimeEntryRevision.revision_number.desc())
            .limit(1)
        )

    async def current_employee_revisions(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_id: UUID,
        start_date: date,
        end_date: date,
    ) -> tuple[WorkdayTimeEntryRevision, ...]:
        newer = WorkdayTimeEntryRevision.__table__.alias("newer_time_revision")
        result = await session.scalars(
            select(WorkdayTimeEntryRevision)
            .where(
                WorkdayTimeEntryRevision.company_id == company_id,
                WorkdayTimeEntryRevision.employee_id == employee_id,
                WorkdayTimeEntryRevision.work_date >= start_date,
                WorkdayTimeEntryRevision.work_date <= end_date,
                ~exists().where(
                    newer.c.company_id == WorkdayTimeEntryRevision.company_id,
                    newer.c.entry_id == WorkdayTimeEntryRevision.entry_id,
                    newer.c.revision_number > WorkdayTimeEntryRevision.revision_number,
                ),
            )
            .order_by(
                WorkdayTimeEntryRevision.work_date, WorkdayTimeEntryRevision.entry_id
            )
        )
        return tuple(result.all())

    async def pay_period_for_date(
        self, session: AsyncSession, *, company_id: UUID, work_date: date
    ) -> PayPeriod | None:
        return await session.scalar(
            select(PayPeriod).where(
                PayPeriod.company_id == company_id,
                PayPeriod.period_start <= work_date,
                PayPeriod.period_end >= work_date,
            )
        )

    async def pay_period_by_id(
        self, session: AsyncSession, *, company_id: UUID, pay_period_id: UUID
    ) -> PayPeriod | None:
        return await session.scalar(
            select(PayPeriod).where(
                PayPeriod.company_id == company_id,
                PayPeriod.id == pay_period_id,
            )
        )

    async def overlapping_pay_period(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> PayPeriod | None:
        return await session.scalar(
            select(PayPeriod).where(
                PayPeriod.company_id == company_id,
                PayPeriod.period_start <= period_end,
                PayPeriod.period_end >= period_start,
            )
        )


timekeeping_repository = TimekeepingRepository()
