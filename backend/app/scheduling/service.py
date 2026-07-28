from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.errors import (
    SchedulingCapacityError,
    SchedulingConflictError,
    SchedulingNotFoundError,
    SchedulingValidationError,
    SchedulingVersionConflictError,
)
from app.scheduling.models import (
    Appointment,
    AppointmentCapacityReservation,
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)
from app.scheduling.repository import (
    CapacityLockContext,
    SchedulingRepository,
    scheduling_repository,
)
from app.scheduling.types import (
    AppointmentCancellationReason,
    AppointmentRescheduleReason,
    AppointmentStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CreateAppointmentCommand:
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    arrival_window_start_at: datetime
    arrival_window_end_at: datetime
    expected_duration_minutes: int
    capacity_units: Decimal = Decimal("1.00")


@dataclass(frozen=True)
class MigrateAppointmentCommand:
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: AppointmentStatus
    arrival_window_start_at: datetime | None
    arrival_window_end_at: datetime | None
    expected_duration_minutes: int | None


@dataclass(frozen=True)
class CancelAppointmentCommand:
    appointment_id: UUID
    expected_version: int
    reason_code: AppointmentCancellationReason


@dataclass(frozen=True)
class RescheduleAppointmentCommand:
    appointment_id: UUID
    expected_version: int
    arrival_window_start_at: datetime
    arrival_window_end_at: datetime
    expected_duration_minutes: int
    capacity_units: Decimal
    reason_code: AppointmentRescheduleReason


@dataclass(frozen=True)
class _CapacityDecision:
    context: CapacityLockContext
    reservation_start_at: datetime
    reservation_end_at: datetime


class SchedulingService:
    """Own Scheduling lifecycle, capacity, transactions, and event staging."""

    def __init__(
        self,
        repository: SchedulingRepository = scheduling_repository,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    async def create_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CreateAppointmentCommand,
    ) -> Appointment:
        self._require_authorized_branch(context, command.branch_id)
        self._validate_window(
            command.arrival_window_start_at,
            command.arrival_window_end_at,
            command.expected_duration_minutes,
            command.capacity_units,
        )
        now = self._clock()
        async with session.begin():
            branch = await self._repository.get_schedulable_branch(
                session,
                company_id=context.company.id,
                branch_id=command.branch_id,
            )
            if branch is None:
                raise SchedulingNotFoundError("Branch", command.branch_id)
            if not await self._repository.references_are_schedulable(
                session,
                company_id=context.company.id,
                customer_id=command.customer_id,
                service_location_id=command.service_location_id,
            ):
                raise SchedulingNotFoundError(
                    "Customer or Service Location", command.customer_id
                )
            decision = await self._reserve_capacity(
                session,
                company_id=context.company.id,
                branch_id=branch.id,
                branch_timezone=branch.timezone,
                window_start_at=command.arrival_window_start_at,
                window_end_at=command.arrival_window_end_at,
                expected_duration_minutes=command.expected_duration_minutes,
                capacity_units=command.capacity_units,
                now=now,
            )
            appointment_number = await self._repository.next_appointment_number(
                session, company_id=context.company.id
            )
            appointment = Appointment(
                id=uuid4(),
                company_id=context.company.id,
                branch_id=branch.id,
                appointment_number=appointment_number,
                customer_id=command.customer_id,
                service_location_id=command.service_location_id,
                status=AppointmentStatus.SCHEDULED.value,
                arrival_window_start_at=command.arrival_window_start_at,
                arrival_window_end_at=command.arrival_window_end_at,
                expected_duration_minutes=command.expected_duration_minutes,
                scheduling_timezone=branch.timezone,
                concurrency_version=1,
                created_by_user_id=context.user.id,
                updated_by_user_id=context.user.id,
                created_at=now,
                updated_at=now,
            )
            await self._repository.create_appointment(session, appointment=appointment)
            reservation = await self._repository.create_capacity_reservation(
                session,
                capacity_context=decision.context,
                reservation=AppointmentCapacityReservation(
                    company_id=context.company.id,
                    branch_id=branch.id,
                    appointment_id=appointment.id,
                    reserved_start_at=decision.reservation_start_at,
                    reserved_end_at=decision.reservation_end_at,
                    capacity_units=command.capacity_units,
                    created_at=now,
                    updated_at=now,
                ),
            )
            appointment.capacity_reservation = reservation
            self._stage_event(
                session,
                context=context,
                branch_id=branch.id,
                appointment=appointment,
                event_type=EventType.APPOINTMENT_CREATED,
                occurred_at=now,
                payload={
                    "appointment_number": appointment.appointment_number,
                    "status": appointment.status,
                    "customer_id": str(appointment.customer_id),
                    "service_location_id": str(appointment.service_location_id),
                    "arrival_window_start_at": command.arrival_window_start_at.isoformat(),
                    "arrival_window_end_at": command.arrival_window_end_at.isoformat(),
                    "schema_version": 1,
                },
            )
            self._stage_event(
                session,
                context=context,
                branch_id=branch.id,
                appointment=appointment,
                event_type=EventType.APPOINTMENT_BOOKED,
                occurred_at=now,
                payload={
                    "appointment_number": appointment.appointment_number,
                    "status": appointment.status,
                    "compatibility_source": EventType.APPOINTMENT_CREATED.value,
                    "schema_version": 1,
                },
            )
        return appointment

    async def stage_migrated_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: MigrateAppointmentCommand,
    ) -> Appointment:
        """Stage one validated migrated Appointment in the caller transaction."""
        self._require_authorized_branch(context, command.branch_id)
        if command.status is AppointmentStatus.CANCELLED:
            raise SchedulingValidationError(
                "Cancelled Appointment lifecycle details are not supported yet."
            )
        committed = command.status in {
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.COMPLETED,
            AppointmentStatus.NO_SHOW,
        }
        if committed and (
            command.arrival_window_start_at is None
            or command.arrival_window_end_at is None
        ):
            raise SchedulingValidationError(
                "Committed Appointments require an arrival window."
            )
        if command.arrival_window_start_at is not None:
            if command.arrival_window_end_at is None:
                raise SchedulingValidationError("Arrival window end is required.")
            self._validate_window(
                command.arrival_window_start_at,
                command.arrival_window_end_at,
                command.expected_duration_minutes or 0,
                Decimal("1.00"),
            )
        elif command.expected_duration_minutes is not None:
            raise SchedulingValidationError(
                "Duration without an arrival window is invalid."
            )
        branch = await self._repository.get_schedulable_branch(
            session,
            company_id=context.company.id,
            branch_id=command.branch_id,
        )
        if branch is None:
            raise SchedulingNotFoundError("Branch", command.branch_id)
        if not await self._repository.references_are_schedulable(
            session,
            company_id=context.company.id,
            customer_id=command.customer_id,
            service_location_id=command.service_location_id,
        ):
            raise SchedulingNotFoundError(
                "Customer or Service Location", command.customer_id
            )
        now = self._clock()
        number = await self._repository.next_appointment_number(
            session, company_id=context.company.id
        )
        appointment = Appointment(
            id=uuid4(),
            company_id=context.company.id,
            branch_id=branch.id,
            appointment_number=number,
            customer_id=command.customer_id,
            service_location_id=command.service_location_id,
            status=command.status.value,
            arrival_window_start_at=command.arrival_window_start_at,
            arrival_window_end_at=command.arrival_window_end_at,
            expected_duration_minutes=command.expected_duration_minutes,
            scheduling_timezone=branch.timezone,
            concurrency_version=1,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
            created_at=now,
            updated_at=now,
        )
        await self._repository.create_appointment(session, appointment=appointment)
        self._stage_event(
            session,
            context=context,
            branch_id=branch.id,
            appointment=appointment,
            event_type=EventType.APPOINTMENT_MIGRATED,
            occurred_at=now,
            payload={
                "appointment_number": appointment.appointment_number,
                "status": appointment.status,
                "origin": "migration",
            },
        )
        return appointment

    async def cancel_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CancelAppointmentCommand,
    ) -> Appointment:
        reason_code = self._validate_reason(
            command.reason_code, AppointmentCancellationReason
        )
        now = self._clock()
        async with session.begin():
            appointment = await self._repository.get_appointment_for_update(
                session,
                company_id=context.company.id,
                appointment_id=command.appointment_id,
            )
            if appointment is None:
                raise SchedulingNotFoundError("Appointment", command.appointment_id)
            self._require_authorized_branch(context, appointment.branch_id)
            if appointment.status == AppointmentStatus.CANCELLED.value:
                if appointment.cancellation_reason_code != reason_code:
                    raise SchedulingConflictError(
                        "Appointment is already cancelled with another reason."
                    )
                return appointment
            if appointment.concurrency_version != command.expected_version:
                raise SchedulingVersionConflictError("Appointment version is stale.")
            if appointment.status not in {
                AppointmentStatus.DRAFT.value,
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value,
            }:
                raise SchedulingConflictError(
                    f"Appointment cannot be cancelled from {appointment.status}."
                )
            reservation = await self._repository.get_capacity_reservation(
                session,
                company_id=context.company.id,
                appointment_id=appointment.id,
                for_update=True,
            )
            appointment.capacity_reservation = reservation
            if reservation is not None and reservation.released_at is None:
                self._repository.release_capacity_reservation(
                    reservation,
                    released_at=now,
                    reason_code="appointment_cancelled",
                )
            self._repository.cancel_appointment(
                appointment,
                cancelled_at=now,
                reason_code=reason_code,
                actor_user_id=context.user.id,
            )
            self._stage_event(
                session,
                context=context,
                branch_id=appointment.branch_id,
                appointment=appointment,
                event_type=EventType.APPOINTMENT_CANCELLED,
                payload={
                    "cancelled_at": now.isoformat(),
                    "reason_code": reason_code,
                    "schema_version": 1,
                },
            )
        return appointment

    async def reschedule_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RescheduleAppointmentCommand,
    ) -> Appointment:
        reason_code = self._validate_reason(
            command.reason_code, AppointmentRescheduleReason
        )
        self._validate_window(
            command.arrival_window_start_at,
            command.arrival_window_end_at,
            command.expected_duration_minutes,
            command.capacity_units,
        )
        now = self._clock()
        async with session.begin():
            current = await self._repository.get_appointment(
                session,
                company_id=context.company.id,
                appointment_id=command.appointment_id,
            )
            if current is None:
                raise SchedulingNotFoundError("Appointment", command.appointment_id)
            self._require_authorized_branch(context, current.branch_id)
            branch = await self._repository.get_schedulable_branch(
                session,
                company_id=context.company.id,
                branch_id=current.branch_id,
            )
            if branch is None:
                raise SchedulingNotFoundError("Branch", current.branch_id)
            capacity_context = await self._repository.lock_capacity_context(
                session,
                company_id=context.company.id,
                branch_id=current.branch_id,
            )
            if capacity_context is None:
                raise SchedulingCapacityError("Branch has no scheduling calendar.")
            appointment = await self._repository.get_appointment_for_update(
                session,
                company_id=context.company.id,
                appointment_id=command.appointment_id,
            )
            if appointment is None:
                raise SchedulingNotFoundError("Appointment", command.appointment_id)
            if appointment.concurrency_version != command.expected_version:
                raise SchedulingVersionConflictError("Appointment version is stale.")
            if appointment.status not in {
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value,
            }:
                raise SchedulingConflictError(
                    f"Appointment cannot be rescheduled from {appointment.status}."
                )
            decision = await self._evaluate_capacity(
                session,
                capacity_context=capacity_context,
                branch_timezone=branch.timezone,
                window_start_at=command.arrival_window_start_at,
                window_end_at=command.arrival_window_end_at,
                expected_duration_minutes=command.expected_duration_minutes,
                capacity_units=command.capacity_units,
                now=now,
                exclude_appointment_id=appointment.id,
            )
            reservation = await self._repository.get_capacity_reservation(
                session,
                company_id=context.company.id,
                appointment_id=appointment.id,
                for_update=True,
            )
            if reservation is None:
                raise SchedulingConflictError(
                    "Scheduled Appointment has no capacity reservation."
                )
            appointment.capacity_reservation = reservation
            previous_start = appointment.arrival_window_start_at
            previous_end = appointment.arrival_window_end_at
            self._repository.move_capacity_reservation(
                reservation,
                reserved_start_at=decision.reservation_start_at,
                reserved_end_at=decision.reservation_end_at,
                capacity_units=command.capacity_units,
                updated_at=now,
            )
            self._repository.reschedule_appointment(
                appointment,
                arrival_window_start_at=command.arrival_window_start_at,
                arrival_window_end_at=command.arrival_window_end_at,
                expected_duration_minutes=command.expected_duration_minutes,
                rescheduled_at=now,
                actor_user_id=context.user.id,
            )
            self._stage_event(
                session,
                context=context,
                branch_id=appointment.branch_id,
                appointment=appointment,
                event_type=EventType.APPOINTMENT_RESCHEDULED,
                payload={
                    "previous_window_start_at": (
                        previous_start.isoformat() if previous_start else None
                    ),
                    "previous_window_end_at": (
                        previous_end.isoformat() if previous_end else None
                    ),
                    "arrival_window_start_at": command.arrival_window_start_at.isoformat(),
                    "arrival_window_end_at": command.arrival_window_end_at.isoformat(),
                    "reason_code": reason_code,
                    "schema_version": 1,
                },
            )
        return appointment

    async def _reserve_capacity(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        branch_timezone: str,
        window_start_at: datetime,
        window_end_at: datetime,
        expected_duration_minutes: int,
        capacity_units: Decimal,
        now: datetime,
    ) -> _CapacityDecision:
        capacity_context = await self._repository.lock_capacity_context(
            session, company_id=company_id, branch_id=branch_id
        )
        if capacity_context is None:
            raise SchedulingCapacityError("Branch has no scheduling calendar.")
        return await self._evaluate_capacity(
            session,
            capacity_context=capacity_context,
            branch_timezone=branch_timezone,
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            expected_duration_minutes=expected_duration_minutes,
            capacity_units=capacity_units,
            now=now,
        )

    async def _evaluate_capacity(
        self,
        session: AsyncSession,
        *,
        capacity_context: CapacityLockContext,
        branch_timezone: str,
        window_start_at: datetime,
        window_end_at: datetime,
        expected_duration_minutes: int,
        capacity_units: Decimal,
        now: datetime,
        exclude_appointment_id: UUID | None = None,
    ) -> _CapacityDecision:
        calendar = await self._repository.get_branch_calendar(
            session,
            company_id=capacity_context.company_id,
            branch_id=capacity_context.branch_id,
        )
        if calendar is None or calendar.id != capacity_context.calendar_id:
            raise SchedulingCapacityError("Scheduling calendar is unavailable.")
        reservation_end = window_start_at + timedelta(minutes=expected_duration_minutes)
        local_start, local_arrival_end, local_work_end = self._validate_calendar_policy(
            calendar,
            branch_timezone=branch_timezone,
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            reservation_end_at=reservation_end,
            now=now,
        )
        intervals = await self._repository.get_weekly_intervals(
            session,
            company_id=capacity_context.company_id,
            branch_id=capacity_context.branch_id,
            calendar_id=capacity_context.calendar_id,
        )
        exceptions = await self._repository.calendar_capacity_for_date(
            session,
            company_id=capacity_context.company_id,
            branch_id=capacity_context.branch_id,
            calendar_id=capacity_context.calendar_id,
            exception_date=local_start.date(),
        )
        start_minute = local_start.hour * 60 + local_start.minute
        self._applicable_capacity(
            calendar,
            intervals=intervals,
            exceptions=exceptions,
            day_of_week=local_start.weekday(),
            start_minute=start_minute,
            end_minute=local_arrival_end.hour * 60 + local_arrival_end.minute,
        )
        available = self._applicable_capacity(
            calendar,
            intervals=intervals,
            exceptions=exceptions,
            day_of_week=local_start.weekday(),
            start_minute=start_minute,
            end_minute=local_work_end.hour * 60 + local_work_end.minute,
        )
        overlaps = await self._repository.get_overlapping_capacity_reservations(
            session,
            capacity_context=capacity_context,
            window_start_at=window_start_at,
            window_end_at=reservation_end,
            exclude_appointment_id=exclude_appointment_id,
            for_update=True,
        )
        reserved = sum(
            (reservation.capacity_units for reservation in overlaps), Decimal("0.00")
        )
        if reserved + capacity_units > available:
            raise SchedulingCapacityError("Insufficient scheduling capacity.")
        return _CapacityDecision(
            context=capacity_context,
            reservation_start_at=window_start_at,
            reservation_end_at=reservation_end,
        )

    @staticmethod
    def _validate_calendar_policy(
        calendar: BranchSchedulingCalendar,
        *,
        branch_timezone: str,
        window_start_at: datetime,
        window_end_at: datetime,
        reservation_end_at: datetime,
        now: datetime,
    ) -> tuple[datetime, datetime, datetime]:
        """Validate arrival and working intervals independently.

        The customer arrival window and the technician working interval both must
        remain within one supported Branch calendar day. Calendar availability and
        closed exceptions are evaluated for each interval by ``_evaluate_capacity``.
        """
        try:
            zone = ZoneInfo(branch_timezone)
        except ZoneInfoNotFoundError as error:
            raise SchedulingValidationError("Branch timezone is invalid.") from error
        if window_start_at < now + timedelta(minutes=calendar.minimum_notice_minutes):
            raise SchedulingValidationError("Arrival window violates minimum notice.")
        if window_start_at > now + timedelta(days=calendar.booking_horizon_days):
            raise SchedulingValidationError("Arrival window exceeds booking horizon.")
        local_start = window_start_at.astimezone(zone)
        local_arrival_end = window_end_at.astimezone(zone)
        local_work_end = reservation_end_at.astimezone(zone)
        if (
            local_start.date() != local_arrival_end.date()
            or local_start.date() != local_work_end.date()
        ):
            raise SchedulingValidationError(
                "Scheduling intervals must remain within one Branch calendar day."
            )
        if (
            (local_start.hour * 60 + local_start.minute)
            % calendar.slot_interval_minutes
            or local_start.second
            or local_start.microsecond
        ):
            raise SchedulingValidationError(
                "Arrival window does not align with the Branch slot interval."
            )
        if window_end_at <= window_start_at:
            raise SchedulingValidationError("Arrival window is invalid.")
        return local_start, local_arrival_end, local_work_end

    @staticmethod
    def _applicable_capacity(
        calendar: BranchSchedulingCalendar,
        *,
        intervals: list[BranchSchedulingWeeklyInterval],
        exceptions: list[BranchSchedulingException],
        day_of_week: int,
        start_minute: int,
        end_minute: int,
    ) -> Decimal:
        closed_exceptions = [
            exception
            for exception in exceptions
            if exception.is_closed
            and (
                exception.start_minute is None
                or exception.end_minute is None
                or (
                    exception.start_minute < end_minute
                    and exception.end_minute > start_minute
                )
            )
        ]
        if closed_exceptions:
            raise SchedulingCapacityError("Branch calendar is closed.")
        exception_capacity = [
            exception.capacity_units
            for exception in exceptions
            if not exception.is_closed
            and exception.capacity_units is not None
            and (
                (exception.start_minute is None and exception.end_minute is None)
                or (
                    exception.start_minute is not None
                    and exception.end_minute is not None
                    and exception.start_minute <= start_minute
                    and exception.end_minute >= end_minute
                )
            )
        ]
        if exception_capacity:
            return min(exception_capacity)
        interval_capacity = [
            interval.capacity_units
            for interval in intervals
            if interval.day_of_week == day_of_week
            and interval.start_minute <= start_minute
            and interval.end_minute >= end_minute
        ]
        if not interval_capacity:
            raise SchedulingCapacityError("Requested interval is not available.")
        return min(min(interval_capacity), calendar.default_capacity_units)

    @staticmethod
    def _validate_window(
        start: datetime,
        end: datetime,
        expected_duration_minutes: int,
        capacity_units: Decimal,
    ) -> None:
        if start.tzinfo is None or end.tzinfo is None:
            raise SchedulingValidationError("Arrival window must be timezone-aware.")
        if end <= start:
            raise SchedulingValidationError("Arrival window end must follow start.")
        if expected_duration_minutes <= 0:
            raise SchedulingValidationError("Expected duration must be positive.")
        if capacity_units <= 0:
            raise SchedulingValidationError("Capacity units must be positive.")

    @staticmethod
    def _validate_reason(
        reason_code: str,
        reason_type: type[AppointmentCancellationReason]
        | type[AppointmentRescheduleReason],
    ) -> str:
        try:
            return reason_type(reason_code).value
        except (TypeError, ValueError) as error:
            raise SchedulingValidationError("Reason code is invalid.") from error

    @staticmethod
    def _require_authorized_branch(
        context: AuthorizationContext, branch_id: UUID
    ) -> None:
        if not context.can_access_branch(branch_id):
            raise SchedulingNotFoundError("Branch", branch_id)

    @staticmethod
    def _stage_event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
        appointment: Appointment,
        event_type: EventType,
        payload: dict[str, object],
        occurred_at: datetime | None = None,
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="appointment",
                entity_id=appointment.id,
                company_id=context.company.id,
                branch_id=branch_id,
                user_id=context.user.id,
                payload=payload,
                occurred_at=occurred_at,
            ),
        )


scheduling_service = SchedulingService()
