from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.scheduling.models import (
    Appointment,
    AppointmentCapacityReservation,
    AppointmentNumberSequence,
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)


@dataclass(frozen=True)
class CapacityLockContext:
    """Proof that the Company/Branch calendar was selected for update."""

    company_id: UUID
    branch_id: UUID
    calendar_id: UUID


class SchedulingRepository:
    """Own Scheduling SQL and locking without committing.

    Future capacity transactions must obtain ``lock_capacity_context`` first,
    read the applicable rules, lock/read overlapping active reservations,
    evaluate capacity, create the reservation, stage events, and only then allow
    the future Scheduling service transaction to commit.
    """

    @staticmethod
    async def next_appointment_number(
        session: AsyncSession, *, company_id: UUID
    ) -> str:
        statement = (
            insert(AppointmentNumberSequence)
            .values(company_id=company_id, last_value=1)
            .on_conflict_do_update(
                index_elements=[AppointmentNumberSequence.company_id],
                set_={
                    "last_value": AppointmentNumberSequence.last_value + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(AppointmentNumberSequence.last_value)
        )
        value = await session.scalar(statement)
        if value is None:
            raise RuntimeError("Appointment number allocation failed")
        return f"APT-{value:06d}"

    @staticmethod
    async def create_appointment(
        session: AsyncSession,
        *,
        appointment: Appointment,
    ) -> Appointment:
        session.add(appointment)
        await session.flush()
        return appointment

    @staticmethod
    async def get_appointment(
        session: AsyncSession,
        *,
        company_id: UUID,
        appointment_id: UUID,
    ) -> Appointment | None:
        return await session.scalar(
            select(Appointment).where(
                Appointment.company_id == company_id,
                Appointment.id == appointment_id,
            )
        )

    @staticmethod
    async def get_appointment_by_number(
        session: AsyncSession,
        *,
        company_id: UUID,
        appointment_number: str,
    ) -> Appointment | None:
        return await session.scalar(
            select(Appointment).where(
                Appointment.company_id == company_id,
                Appointment.appointment_number == appointment_number,
            )
        )

    @staticmethod
    async def get_appointment_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        appointment_id: UUID,
    ) -> Appointment | None:
        return await session.scalar(
            select(Appointment)
            .where(
                Appointment.company_id == company_id,
                Appointment.id == appointment_id,
            )
            .with_for_update()
        )

    @staticmethod
    async def appointment_number_exists(
        session: AsyncSession,
        *,
        company_id: UUID,
        appointment_number: str,
    ) -> bool:
        return bool(
            await session.scalar(
                select(
                    select(Appointment.id)
                    .where(
                        Appointment.company_id == company_id,
                        Appointment.appointment_number == appointment_number,
                    )
                    .exists()
                )
            )
        )

    @staticmethod
    async def create_capacity_reservation(
        session: AsyncSession,
        *,
        capacity_context: CapacityLockContext,
        reservation: AppointmentCapacityReservation,
    ) -> AppointmentCapacityReservation:
        if (
            reservation.company_id != capacity_context.company_id
            or reservation.branch_id != capacity_context.branch_id
        ):
            raise ValueError("Capacity reservation does not match the locked calendar")
        session.add(reservation)
        await session.flush()
        return reservation

    @staticmethod
    async def get_capacity_reservation(
        session: AsyncSession,
        *,
        company_id: UUID,
        appointment_id: UUID,
        for_update: bool = False,
    ) -> AppointmentCapacityReservation | None:
        statement = select(AppointmentCapacityReservation).where(
            AppointmentCapacityReservation.company_id == company_id,
            AppointmentCapacityReservation.appointment_id == appointment_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    async def get_overlapping_capacity_reservations(
        session: AsyncSession,
        *,
        capacity_context: CapacityLockContext,
        window_start_at: datetime,
        window_end_at: datetime,
        exclude_appointment_id: UUID | None = None,
        for_update: bool = False,
    ) -> list[AppointmentCapacityReservation]:
        statement = (
            select(AppointmentCapacityReservation)
            .where(
                AppointmentCapacityReservation.company_id
                == capacity_context.company_id,
                AppointmentCapacityReservation.branch_id == capacity_context.branch_id,
                AppointmentCapacityReservation.released_at.is_(None),
                AppointmentCapacityReservation.reserved_start_at < window_end_at,
                AppointmentCapacityReservation.reserved_end_at > window_start_at,
            )
            .order_by(
                AppointmentCapacityReservation.reserved_start_at,
                AppointmentCapacityReservation.id,
            )
        )
        if exclude_appointment_id is not None:
            statement = statement.where(
                AppointmentCapacityReservation.appointment_id != exclude_appointment_id
            )
        if for_update:
            statement = statement.with_for_update()
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def create_branch_calendar(
        session: AsyncSession,
        *,
        calendar: BranchSchedulingCalendar,
    ) -> BranchSchedulingCalendar:
        session.add(calendar)
        await session.flush()
        return calendar

    @staticmethod
    async def get_branch_calendar(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        for_update: bool = False,
    ) -> BranchSchedulingCalendar | None:
        statement = select(BranchSchedulingCalendar).where(
            BranchSchedulingCalendar.company_id == company_id,
            BranchSchedulingCalendar.branch_id == branch_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @classmethod
    async def lock_capacity_context(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
    ) -> CapacityLockContext | None:
        """Lock the single Company/Branch calendar before capacity evaluation."""
        calendar = await cls.get_branch_calendar(
            session,
            company_id=company_id,
            branch_id=branch_id,
            for_update=True,
        )
        if calendar is None:
            return None
        return CapacityLockContext(
            company_id=calendar.company_id,
            branch_id=calendar.branch_id,
            calendar_id=calendar.id,
        )

    @staticmethod
    async def add_weekly_interval(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        interval: BranchSchedulingWeeklyInterval,
    ) -> BranchSchedulingWeeklyInterval | None:
        calendar_exists = await session.scalar(
            select(
                select(BranchSchedulingCalendar.id)
                .where(
                    BranchSchedulingCalendar.id == interval.calendar_id,
                    BranchSchedulingCalendar.company_id == company_id,
                    BranchSchedulingCalendar.branch_id == branch_id,
                )
                .exists()
            )
        )
        if not calendar_exists:
            return None
        session.add(interval)
        await session.flush()
        return interval

    @staticmethod
    async def add_calendar_exception(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        exception: BranchSchedulingException,
    ) -> BranchSchedulingException | None:
        calendar_exists = await session.scalar(
            select(
                select(BranchSchedulingCalendar.id)
                .where(
                    BranchSchedulingCalendar.id == exception.calendar_id,
                    BranchSchedulingCalendar.company_id == company_id,
                    BranchSchedulingCalendar.branch_id == branch_id,
                )
                .exists()
            )
        )
        if not calendar_exists:
            return None
        session.add(exception)
        await session.flush()
        return exception

    @staticmethod
    async def get_weekly_intervals(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        calendar_id: UUID,
    ) -> list[BranchSchedulingWeeklyInterval]:
        return list(
            (
                await session.scalars(
                    select(BranchSchedulingWeeklyInterval)
                    .join(BranchSchedulingWeeklyInterval.calendar)
                    .where(
                        BranchSchedulingCalendar.company_id == company_id,
                        BranchSchedulingCalendar.branch_id == branch_id,
                        BranchSchedulingWeeklyInterval.calendar_id == calendar_id,
                    )
                    .order_by(
                        BranchSchedulingWeeklyInterval.day_of_week,
                        BranchSchedulingWeeklyInterval.start_minute,
                        BranchSchedulingWeeklyInterval.id,
                    )
                )
            ).all()
        )

    @staticmethod
    async def calendar_capacity_for_date(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        calendar_id: UUID,
        exception_date: date,
    ) -> list[BranchSchedulingException]:
        return list(
            (
                await session.scalars(
                    select(BranchSchedulingException)
                    .join(BranchSchedulingException.calendar)
                    .where(
                        BranchSchedulingCalendar.company_id == company_id,
                        BranchSchedulingCalendar.branch_id == branch_id,
                        BranchSchedulingException.calendar_id == calendar_id,
                        BranchSchedulingException.exception_date == exception_date,
                    )
                    .order_by(
                        BranchSchedulingException.start_minute,
                        BranchSchedulingException.id,
                    )
                )
            ).all()
        )


scheduling_repository = SchedulingRepository()
