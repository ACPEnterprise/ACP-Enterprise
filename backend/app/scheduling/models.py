from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.customers.models import Customer, ServiceLocation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AppointmentNumberSequence(Base):
    __tablename__ = "appointment_number_sequences"
    __table_args__ = (
        CheckConstraint(
            "last_value >= 0",
            name="ck_appointment_number_sequences_last_value",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_appointment_number_sequences_company_id_companies",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class BranchSchedulingCalendar(Base):
    __tablename__ = "branch_scheduling_calendars"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_branch_scheduling_calendars_company_branch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            name="uq_branch_scheduling_calendars_company_branch",
        ),
        CheckConstraint(
            "booking_horizon_days > 0",
            name="ck_branch_scheduling_calendars_booking_horizon",
        ),
        CheckConstraint(
            "minimum_notice_minutes >= 0",
            name="ck_branch_scheduling_calendars_minimum_notice",
        ),
        CheckConstraint(
            "slot_interval_minutes > 0 AND slot_interval_minutes <= 1440",
            name="ck_branch_scheduling_calendars_slot_interval",
        ),
        CheckConstraint(
            "default_capacity_units > 0",
            name="ck_branch_scheduling_calendars_default_capacity",
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_branch_scheduling_calendars_concurrency_version",
        ),
        Index(
            "ix_branch_scheduling_calendars_company_branch",
            "company_id",
            "branch_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_branch_scheduling_calendars_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    booking_horizon_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365
    )
    minimum_notice_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    slot_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    default_capacity_units: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("1.00")
    )
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_branch_scheduling_calendars_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_branch_scheduling_calendars_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )

    weekly_intervals: Mapped[list["BranchSchedulingWeeklyInterval"]] = relationship(
        back_populates="calendar", passive_deletes=True
    )
    exceptions: Mapped[list["BranchSchedulingException"]] = relationship(
        back_populates="calendar", passive_deletes=True
    )


class BranchSchedulingWeeklyInterval(Base):
    __tablename__ = "branch_scheduling_weekly_intervals"
    __table_args__ = (
        CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="ck_branch_scheduling_weekly_intervals_day_of_week",
        ),
        CheckConstraint(
            "start_minute >= 0 AND start_minute < 1440",
            name="ck_branch_scheduling_weekly_intervals_start_minute",
        ),
        CheckConstraint(
            "end_minute > 0 AND end_minute <= 1440 AND end_minute > start_minute",
            name="ck_branch_scheduling_weekly_intervals_end_minute",
        ),
        CheckConstraint(
            "capacity_units > 0",
            name="ck_branch_scheduling_weekly_intervals_capacity",
        ),
        UniqueConstraint(
            "calendar_id",
            "day_of_week",
            "start_minute",
            "end_minute",
            name="uq_branch_scheduling_weekly_intervals_window",
        ),
        Index(
            "ix_branch_scheduling_weekly_intervals_calendar_day",
            "calendar_id",
            "day_of_week",
            "start_minute",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    calendar_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "branch_scheduling_calendars.id",
            name="fk_branch_scheduling_weekly_intervals_calendar_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_minute: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    end_minute: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    capacity_units: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    calendar: Mapped[BranchSchedulingCalendar] = relationship(
        back_populates="weekly_intervals"
    )


class BranchSchedulingException(Base):
    __tablename__ = "branch_scheduling_exceptions"
    __table_args__ = (
        CheckConstraint(
            "(start_minute IS NULL AND end_minute IS NULL) OR "
            "(start_minute >= 0 AND start_minute < 1440 "
            "AND end_minute > 0 AND end_minute <= 1440 "
            "AND end_minute > start_minute)",
            name="ck_branch_scheduling_exceptions_window",
        ),
        CheckConstraint(
            "(is_closed = true AND capacity_units IS NULL) OR "
            "(is_closed = false AND capacity_units > 0)",
            name="ck_branch_scheduling_exceptions_capacity",
        ),
        CheckConstraint(
            "length(btrim(reason_code)) > 0",
            name="ck_branch_scheduling_exceptions_reason_not_blank",
        ),
        Index(
            "ix_branch_scheduling_exceptions_calendar_date",
            "calendar_id",
            "exception_date",
            "start_minute",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    calendar_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "branch_scheduling_calendars.id",
            name="fk_branch_scheduling_exceptions_calendar_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    exception_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_minute: Mapped[int | None] = mapped_column(SmallInteger)
    end_minute: Mapped[int | None] = mapped_column(SmallInteger)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    capacity_units: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    calendar: Mapped[BranchSchedulingCalendar] = relationship(
        back_populates="exceptions"
    )


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_appointments_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "customer_id"],
            ["customers.company_id", "customers.id"],
            name="fk_appointments_customer_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_appointments_location_customer",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "appointment_number ~ '^APT-[0-9]{6,}$'",
            name="ck_appointments_number_format",
        ),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'confirmed', 'cancelled', "
            "'completed', 'no_show')",
            name="ck_appointments_status",
        ),
        CheckConstraint(
            "(arrival_window_start_at IS NULL AND arrival_window_end_at IS NULL) "
            "OR (arrival_window_start_at IS NOT NULL "
            "AND arrival_window_end_at IS NOT NULL "
            "AND arrival_window_end_at > arrival_window_start_at)",
            name="ck_appointments_arrival_window",
        ),
        CheckConstraint(
            "status NOT IN ('scheduled', 'confirmed', 'completed', 'no_show') "
            "OR arrival_window_start_at IS NOT NULL",
            name="ck_appointments_committed_window_required",
        ),
        CheckConstraint(
            "expected_duration_minutes IS NULL OR expected_duration_minutes > 0",
            name="ck_appointments_expected_duration",
        ),
        CheckConstraint(
            "length(btrim(scheduling_timezone)) > 0",
            name="ck_appointments_scheduling_timezone_not_blank",
        ),
        CheckConstraint(
            "concurrency_version >= 1",
            name="ck_appointments_concurrency_version",
        ),
        CheckConstraint(
            "reschedule_count >= 0",
            name="ck_appointments_reschedule_count",
        ),
        CheckConstraint(
            "(reschedule_count = 0 AND rescheduled_at IS NULL "
            "AND rescheduled_by_user_id IS NULL) OR "
            "(reschedule_count > 0 AND rescheduled_at IS NOT NULL)",
            name="ck_appointments_reschedule_state",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancellation_reason_code IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL "
            "AND cancellation_reason_code IS NULL "
            "AND cancelled_by_user_id IS NULL)",
            name="ck_appointments_cancellation_state",
        ),
        CheckConstraint(
            "cancellation_reason_code IS NULL OR "
            "length(btrim(cancellation_reason_code)) > 0",
            name="ck_appointments_cancellation_reason_not_blank",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_appointments_updated_after_created",
        ),
        UniqueConstraint(
            "company_id",
            "appointment_number",
            name="uq_appointments_company_number",
        ),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            name="uq_appointments_company_branch_id",
        ),
        Index(
            "ix_appointments_company_branch_window",
            "company_id",
            "branch_id",
            "arrival_window_start_at",
            "id",
        ),
        Index(
            "ix_appointments_company_status_window",
            "company_id",
            "status",
            "arrival_window_start_at",
            "id",
        ),
        Index("ix_appointments_customer_id", "customer_id"),
        Index("ix_appointments_service_location_id", "service_location_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_appointments_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_number: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    service_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    arrival_window_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    arrival_window_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    expected_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    scheduling_timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reschedule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rescheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rescheduled_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_appointments_rescheduled_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason_code: Mapped[str | None] = mapped_column(String(80))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_appointments_cancelled_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_appointments_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_appointments_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )

    customer: Mapped["Customer"] = relationship(foreign_keys=[customer_id])
    service_location: Mapped["ServiceLocation"] = relationship(
        foreign_keys=[service_location_id]
    )
    capacity_reservation: Mapped["AppointmentCapacityReservation | None"] = (
        relationship(back_populates="appointment", passive_deletes=True, uselist=False)
    )


class AppointmentCapacityReservation(Base):
    __tablename__ = "appointment_capacity_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_appointment_capacity_reservations_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_appointment_capacity_reservations_appointment",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "reserved_end_at > reserved_start_at",
            name="ck_appointment_capacity_reservations_window",
        ),
        CheckConstraint(
            "capacity_units > 0",
            name="ck_appointment_capacity_reservations_capacity",
        ),
        CheckConstraint(
            "(released_at IS NULL AND release_reason_code IS NULL) OR "
            "(released_at IS NOT NULL AND release_reason_code IS NOT NULL)",
            name="ck_appointment_capacity_reservations_release_state",
        ),
        CheckConstraint(
            "release_reason_code IS NULL OR length(btrim(release_reason_code)) > 0",
            name="ck_appointment_capacity_reservations_release_reason_not_blank",
        ),
        CheckConstraint(
            "(is_override = false AND override_reason_code IS NULL "
            "AND overridden_at IS NULL AND overridden_by_user_id IS NULL) OR "
            "(is_override = true AND override_reason_code IS NOT NULL "
            "AND overridden_at IS NOT NULL)",
            name="ck_appointment_capacity_reservations_override_state",
        ),
        CheckConstraint(
            "override_reason_code IS NULL OR length(btrim(override_reason_code)) > 0",
            name="ck_appointment_capacity_reservations_override_reason_not_blank",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_appointment_capacity_reservations_updated_after_created",
        ),
        UniqueConstraint(
            "appointment_id",
            name="uq_appointment_capacity_reservations_appointment_id",
        ),
        Index(
            "ix_appointment_capacity_reservations_active_window",
            "company_id",
            "branch_id",
            "reserved_start_at",
            "reserved_end_at",
            "id",
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            name="fk_appointment_capacity_reservations_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reserved_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reserved_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    capacity_units: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason_code: Mapped[str | None] = mapped_column(String(80))
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overridden_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_capacity_reservations_overridden_by_user_id_users",
            ondelete="RESTRICT",
        ),
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    appointment: Mapped[Appointment] = relationship(
        back_populates="capacity_reservation",
        primaryjoin=(
            "and_(AppointmentCapacityReservation.company_id == Appointment.company_id, "
            "AppointmentCapacityReservation.branch_id == Appointment.branch_id, "
            "AppointmentCapacityReservation.appointment_id == Appointment.id)"
        ),
        foreign_keys=[company_id, branch_id, appointment_id],
    )
