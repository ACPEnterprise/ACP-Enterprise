from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.customers.models import Customer, ServiceLocation
from app.platform.branch.models import Branch
from app.scheduling.models import (
    Appointment,
    AppointmentCapacityReservation,
    AppointmentNumberSequence,
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)
from app.scheduling.query import AppointmentQuery, AppointmentQueryRecord
from app.scheduling.types import AppointmentStatus


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
    def _query_record_statement():
        return select(
            Appointment.id,
            Appointment.appointment_number,
            Appointment.company_id,
            Appointment.branch_id,
            Appointment.customer_id,
            Appointment.service_location_id,
            Appointment.status,
            Appointment.arrival_window_start_at,
            Appointment.arrival_window_end_at,
            Appointment.expected_duration_minutes,
            AppointmentCapacityReservation.capacity_units,
            Appointment.concurrency_version,
            Appointment.reschedule_count,
            Appointment.rescheduled_at,
            Appointment.cancelled_at,
            Appointment.cancellation_reason_code,
            Appointment.created_at,
            Appointment.updated_at,
        ).outerjoin(
            AppointmentCapacityReservation,
            (AppointmentCapacityReservation.company_id == Appointment.company_id)
            & (AppointmentCapacityReservation.branch_id == Appointment.branch_id)
            & (AppointmentCapacityReservation.appointment_id == Appointment.id),
        )

    @staticmethod
    def _query_record(values: RowMapping) -> AppointmentQueryRecord:
        return AppointmentQueryRecord(
            id=values["id"],
            appointment_number=values["appointment_number"],
            company_id=values["company_id"],
            branch_id=values["branch_id"],
            customer_id=values["customer_id"],
            service_location_id=values["service_location_id"],
            status=AppointmentStatus(values["status"]),
            arrival_window_start_at=values["arrival_window_start_at"],
            arrival_window_end_at=values["arrival_window_end_at"],
            expected_duration_minutes=values["expected_duration_minutes"],
            capacity_units=values["capacity_units"],
            concurrency_version=values["concurrency_version"],
            reschedule_count=values["reschedule_count"],
            rescheduled_at=values["rescheduled_at"],
            cancelled_at=values["cancelled_at"],
            cancellation_reason_code=values["cancellation_reason_code"],
            created_at=values["created_at"],
            updated_at=values["updated_at"],
        )

    @classmethod
    async def get_appointment_query_record(
        cls,
        session: AsyncSession,
        *,
        query: AppointmentQuery,
    ) -> AppointmentQueryRecord | None:
        if not query.authorized_branch_ids or query.appointment_id is None:
            return None
        row = (
            (
                await session.execute(
                    cls._query_record_statement().where(
                        Appointment.company_id == query.company_id,
                        Appointment.branch_id.in_(query.authorized_branch_ids),
                        Appointment.id == query.appointment_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return cls._query_record(row) if row is not None else None

    @classmethod
    async def search_appointment_query_records(
        cls,
        session: AsyncSession,
        *,
        query: AppointmentQuery,
    ) -> tuple[tuple[AppointmentQueryRecord, ...], int]:
        if not query.authorized_branch_ids:
            return (), 0
        if query.start_at is None or query.end_at is None:
            raise ValueError("Calendar query requires a range")
        filters = [
            Appointment.company_id == query.company_id,
            Appointment.branch_id.in_(query.authorized_branch_ids),
            Appointment.arrival_window_start_at.is_not(None),
            Appointment.arrival_window_end_at.is_not(None),
            Appointment.arrival_window_start_at < query.end_at,
            Appointment.arrival_window_end_at > query.start_at,
        ]
        if query.branch_id is not None:
            filters.append(Appointment.branch_id == query.branch_id)
        if query.statuses:
            filters.append(
                Appointment.status.in_(status.value for status in query.statuses)
            )
        if query.customer_id is not None:
            filters.append(Appointment.customer_id == query.customer_id)
        if query.service_location_id is not None:
            filters.append(Appointment.service_location_id == query.service_location_id)
        total = int(
            await session.scalar(
                select(func.count()).select_from(Appointment).where(*filters)
            )
            or 0
        )
        rows = (
            (
                await session.execute(
                    cls._query_record_statement()
                    .where(*filters)
                    .order_by(
                        Appointment.arrival_window_start_at,
                        Appointment.arrival_window_end_at,
                        Appointment.appointment_number,
                        Appointment.id,
                    )
                    .limit(query.page_size)
                    .offset((query.page - 1) * query.page_size)
                )
            )
            .mappings()
            .all()
        )
        return tuple(cls._query_record(row) for row in rows), total

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
            .options(selectinload(Appointment.capacity_reservation))
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
    async def get_schedulable_branch(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
    ) -> Branch | None:
        """Load an active, unarchived Branch without taking ownership of it."""
        return await session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.status == "active",
                Branch.archived_at.is_(None),
            )
        )

    @staticmethod
    async def references_are_schedulable(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_id: UUID,
        service_location_id: UUID,
    ) -> bool:
        """Validate active external references without mutating their domains."""
        return bool(
            await session.scalar(
                select(
                    select(ServiceLocation.id)
                    .join(Customer, Customer.id == ServiceLocation.customer_id)
                    .where(
                        Customer.id == customer_id,
                        Customer.company_id == company_id,
                        Customer.status == "active",
                        Customer.archived_at.is_(None),
                        ServiceLocation.id == service_location_id,
                        ServiceLocation.customer_id == customer_id,
                        ServiceLocation.active.is_(True),
                        ServiceLocation.archived_at.is_(None),
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
    def release_capacity_reservation(
        reservation: AppointmentCapacityReservation,
        *,
        released_at: datetime,
        reason_code: str,
    ) -> None:
        reservation.released_at = released_at
        reservation.release_reason_code = reason_code
        reservation.updated_at = released_at

    @staticmethod
    def move_capacity_reservation(
        reservation: AppointmentCapacityReservation,
        *,
        reserved_start_at: datetime,
        reserved_end_at: datetime,
        capacity_units: Decimal,
        updated_at: datetime,
    ) -> None:
        reservation.reserved_start_at = reserved_start_at
        reservation.reserved_end_at = reserved_end_at
        reservation.capacity_units = capacity_units
        reservation.released_at = None
        reservation.release_reason_code = None
        reservation.updated_at = updated_at

    @staticmethod
    def cancel_appointment(
        appointment: Appointment,
        *,
        cancelled_at: datetime,
        reason_code: str,
        actor_user_id: UUID,
    ) -> None:
        appointment.status = "cancelled"
        appointment.cancelled_at = cancelled_at
        appointment.cancellation_reason_code = reason_code
        appointment.cancelled_by_user_id = actor_user_id
        appointment.updated_by_user_id = actor_user_id
        appointment.updated_at = cancelled_at
        appointment.concurrency_version += 1

    @staticmethod
    def reschedule_appointment(
        appointment: Appointment,
        *,
        arrival_window_start_at: datetime,
        arrival_window_end_at: datetime,
        expected_duration_minutes: int,
        rescheduled_at: datetime,
        actor_user_id: UUID,
    ) -> None:
        appointment.arrival_window_start_at = arrival_window_start_at
        appointment.arrival_window_end_at = arrival_window_end_at
        appointment.expected_duration_minutes = expected_duration_minutes
        appointment.reschedule_count += 1
        appointment.rescheduled_at = rescheduled_at
        appointment.rescheduled_by_user_id = actor_user_id
        appointment.updated_by_user_id = actor_user_id
        appointment.updated_at = rescheduled_at
        appointment.concurrency_version += 1

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
