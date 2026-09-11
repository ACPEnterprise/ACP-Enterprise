"""Company-scoped persistence queries for Workday Time."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    JobWorkedClockEvent,
    JobWorkedIntervalRevision,
    PayPeriod,
    WorkdayPunchEvent,
    WorkdayTimeEntryRevision,
)


class TimekeepingRepository:
    async def lock_employee_job_clock(
        self, session: AsyncSession, *, company_id: UUID, employee_id: UUID
    ) -> None:
        lock_key = (company_id.int ^ employee_id.int) & ((1 << 63) - 1)
        await session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def job_scope_exists(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        job_id: UUID,
        appointment_id: UUID | None,
    ) -> bool:
        from app.jobs.models import Job, JobAppointmentLink

        if not await session.scalar(
            select(
                exists().where(
                    Job.company_id == company_id,
                    Job.branch_id == branch_id,
                    Job.id == job_id,
                )
            )
        ):
            return False
        if appointment_id is None:
            return True
        return bool(
            await session.scalar(
                select(
                    exists().where(
                        JobAppointmentLink.company_id == company_id,
                        JobAppointmentLink.branch_id == branch_id,
                        JobAppointmentLink.job_id == job_id,
                        JobAppointmentLink.appointment_id == appointment_id,
                    )
                )
            )
        )

    async def latest_job_clock_event(
        self, session: AsyncSession, *, company_id: UUID, employee_id: UUID
    ) -> JobWorkedClockEvent | None:
        return await session.scalar(
            select(JobWorkedClockEvent)
            .where(
                JobWorkedClockEvent.company_id == company_id,
                JobWorkedClockEvent.employee_id == employee_id,
            )
            .order_by(
                JobWorkedClockEvent.occurred_at.desc(), JobWorkedClockEvent.id.desc()
            )
            .limit(1)
        )

    async def job_clock_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        recorded_by_user_id: UUID,
        idempotency_key: str,
    ) -> JobWorkedClockEvent | None:
        return await session.scalar(
            select(JobWorkedClockEvent).where(
                JobWorkedClockEvent.company_id == company_id,
                JobWorkedClockEvent.recorded_by_user_id == recorded_by_user_id,
                JobWorkedClockEvent.idempotency_key == idempotency_key,
            )
        )

    async def interval_for_job_clock_event(
        self, session: AsyncSession, *, company_id: UUID, event_id: UUID
    ) -> JobWorkedIntervalRevision | None:
        return await session.scalar(
            select(JobWorkedIntervalRevision)
            .where(
                JobWorkedIntervalRevision.company_id == company_id,
                JobWorkedIntervalRevision.source_event_ids.contains([str(event_id)]),
            )
            .order_by(JobWorkedIntervalRevision.revision_number.desc())
            .limit(1)
        )

    async def latest_job_interval_revision(
        self, session: AsyncSession, *, company_id: UUID, revision_id: UUID
    ) -> JobWorkedIntervalRevision | None:
        base = await session.scalar(
            select(JobWorkedIntervalRevision).where(
                JobWorkedIntervalRevision.company_id == company_id,
                JobWorkedIntervalRevision.id == revision_id,
            )
        )
        if base is None:
            return None
        return await session.scalar(
            select(JobWorkedIntervalRevision)
            .where(
                JobWorkedIntervalRevision.company_id == company_id,
                JobWorkedIntervalRevision.interval_id == base.interval_id,
            )
            .order_by(JobWorkedIntervalRevision.revision_number.desc())
            .limit(1)
        )

    async def job_interval_correction_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        corrected_by_user_id: UUID,
        idempotency_key: str,
    ) -> JobWorkedIntervalRevision | None:
        return await session.scalar(
            select(JobWorkedIntervalRevision).where(
                JobWorkedIntervalRevision.company_id == company_id,
                JobWorkedIntervalRevision.corrected_by_user_id == corrected_by_user_id,
                JobWorkedIntervalRevision.correction_idempotency_key == idempotency_key,
            )
        )

    async def current_job_intervals(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_ids: tuple[UUID, ...],
        start_at: datetime,
        stop_at: datetime,
    ) -> tuple[JobWorkedIntervalRevision, ...]:
        if not employee_ids:
            return ()
        newer = JobWorkedIntervalRevision.__table__.alias("newer_job_interval")
        values = await session.scalars(
            select(JobWorkedIntervalRevision).where(
                JobWorkedIntervalRevision.company_id == company_id,
                JobWorkedIntervalRevision.employee_id.in_(employee_ids),
                JobWorkedIntervalRevision.stop_at > start_at,
                JobWorkedIntervalRevision.start_at < stop_at,
                ~exists().where(
                    newer.c.company_id == JobWorkedIntervalRevision.company_id,
                    newer.c.interval_id == JobWorkedIntervalRevision.interval_id,
                    newer.c.revision_number > JobWorkedIntervalRevision.revision_number,
                ),
            )
        )
        return tuple(values.all())

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

    async def correction_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        responsible_user_id: UUID,
        idempotency_key: str,
    ) -> WorkdayTimeEntryRevision | None:
        return await session.scalar(
            select(WorkdayTimeEntryRevision).where(
                WorkdayTimeEntryRevision.company_id == company_id,
                WorkdayTimeEntryRevision.responsible_user_id == responsible_user_id,
                WorkdayTimeEntryRevision.correction_idempotency_key == idempotency_key,
            )
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
