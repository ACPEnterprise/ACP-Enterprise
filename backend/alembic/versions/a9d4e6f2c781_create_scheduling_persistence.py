"""create scheduling persistence

Revision ID: a9d4e6f2c781
Revises: f2c8a4e6b193
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a9d4e6f2c781"
down_revision: str | None = "f2c8a4e6b193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appointment_number_sequences",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "last_value >= 0",
            name="ck_appointment_number_sequences_last_value",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_appointment_number_sequences_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", name="pk_appointment_number_sequences"),
    )

    op.create_table(
        "branch_scheduling_calendars",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_horizon_days", sa.Integer(), nullable=False),
        sa.Column("minimum_notice_minutes", sa.Integer(), nullable=False),
        sa.Column("slot_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("default_capacity_units", sa.Numeric(10, 2), nullable=False),
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "booking_horizon_days > 0",
            name="ck_branch_scheduling_calendars_booking_horizon",
        ),
        sa.CheckConstraint(
            "minimum_notice_minutes >= 0",
            name="ck_branch_scheduling_calendars_minimum_notice",
        ),
        sa.CheckConstraint(
            "slot_interval_minutes > 0 AND slot_interval_minutes <= 1440",
            name="ck_branch_scheduling_calendars_slot_interval",
        ),
        sa.CheckConstraint(
            "default_capacity_units > 0",
            name="ck_branch_scheduling_calendars_default_capacity",
        ),
        sa.CheckConstraint(
            "concurrency_version >= 1",
            name="ck_branch_scheduling_calendars_concurrency_version",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_branch_scheduling_calendars_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_branch_scheduling_calendars_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_branch_scheduling_calendars_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_branch_scheduling_calendars_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_branch_scheduling_calendars"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            name="uq_branch_scheduling_calendars_company_branch",
        ),
    )
    op.create_index(
        "ix_branch_scheduling_calendars_company_branch",
        "branch_scheduling_calendars",
        ["company_id", "branch_id"],
    )

    op.create_table(
        "branch_scheduling_weekly_intervals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("calendar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("start_minute", sa.SmallInteger(), nullable=False),
        sa.Column("end_minute", sa.SmallInteger(), nullable=False),
        sa.Column("capacity_units", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="ck_branch_scheduling_weekly_intervals_day_of_week",
        ),
        sa.CheckConstraint(
            "start_minute >= 0 AND start_minute < 1440",
            name="ck_branch_scheduling_weekly_intervals_start_minute",
        ),
        sa.CheckConstraint(
            "end_minute > 0 AND end_minute <= 1440 AND end_minute > start_minute",
            name="ck_branch_scheduling_weekly_intervals_end_minute",
        ),
        sa.CheckConstraint(
            "capacity_units > 0",
            name="ck_branch_scheduling_weekly_intervals_capacity",
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["branch_scheduling_calendars.id"],
            name="fk_branch_scheduling_weekly_intervals_calendar_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_branch_scheduling_weekly_intervals"),
        sa.UniqueConstraint(
            "calendar_id",
            "day_of_week",
            "start_minute",
            "end_minute",
            name="uq_branch_scheduling_weekly_intervals_window",
        ),
    )
    op.create_index(
        "ix_branch_scheduling_weekly_intervals_calendar_day",
        "branch_scheduling_weekly_intervals",
        ["calendar_id", "day_of_week", "start_minute"],
    )

    op.create_table(
        "branch_scheduling_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("calendar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exception_date", sa.Date(), nullable=False),
        sa.Column("start_minute", sa.SmallInteger(), nullable=True),
        sa.Column("end_minute", sa.SmallInteger(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("capacity_units", sa.Numeric(10, 2), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(start_minute IS NULL AND end_minute IS NULL) OR "
            "(start_minute >= 0 AND start_minute < 1440 "
            "AND end_minute > 0 AND end_minute <= 1440 "
            "AND end_minute > start_minute)",
            name="ck_branch_scheduling_exceptions_window",
        ),
        sa.CheckConstraint(
            "(is_closed = true AND capacity_units IS NULL) OR "
            "(is_closed = false AND capacity_units > 0)",
            name="ck_branch_scheduling_exceptions_capacity",
        ),
        sa.CheckConstraint(
            "length(btrim(reason_code)) > 0",
            name="ck_branch_scheduling_exceptions_reason_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["branch_scheduling_calendars.id"],
            name="fk_branch_scheduling_exceptions_calendar_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_branch_scheduling_exceptions"),
    )
    op.create_index(
        "ix_branch_scheduling_exceptions_calendar_date",
        "branch_scheduling_exceptions",
        ["calendar_id", "exception_date", "start_minute"],
    )

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_number", sa.String(length=24), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("arrival_window_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrival_window_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("scheduling_timezone", sa.String(length=100), nullable=False),
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("reschedule_count", sa.Integer(), nullable=False),
        sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rescheduled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason_code", sa.String(length=80), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "appointment_number ~ '^APT-[0-9]{6,}$'",
            name="ck_appointments_number_format",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'confirmed', 'cancelled', "
            "'completed', 'no_show')",
            name="ck_appointments_status",
        ),
        sa.CheckConstraint(
            "(arrival_window_start_at IS NULL AND arrival_window_end_at IS NULL) "
            "OR (arrival_window_start_at IS NOT NULL "
            "AND arrival_window_end_at IS NOT NULL "
            "AND arrival_window_end_at > arrival_window_start_at)",
            name="ck_appointments_arrival_window",
        ),
        sa.CheckConstraint(
            "status NOT IN ('scheduled', 'confirmed', 'completed', 'no_show') "
            "OR arrival_window_start_at IS NOT NULL",
            name="ck_appointments_committed_window_required",
        ),
        sa.CheckConstraint(
            "expected_duration_minutes IS NULL OR expected_duration_minutes > 0",
            name="ck_appointments_expected_duration",
        ),
        sa.CheckConstraint(
            "length(btrim(scheduling_timezone)) > 0",
            name="ck_appointments_scheduling_timezone_not_blank",
        ),
        sa.CheckConstraint(
            "concurrency_version >= 1",
            name="ck_appointments_concurrency_version",
        ),
        sa.CheckConstraint(
            "reschedule_count >= 0", name="ck_appointments_reschedule_count"
        ),
        sa.CheckConstraint(
            "(reschedule_count = 0 AND rescheduled_at IS NULL "
            "AND rescheduled_by_user_id IS NULL) OR "
            "(reschedule_count > 0 AND rescheduled_at IS NOT NULL)",
            name="ck_appointments_reschedule_state",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancellation_reason_code IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL "
            "AND cancellation_reason_code IS NULL "
            "AND cancelled_by_user_id IS NULL)",
            name="ck_appointments_cancellation_state",
        ),
        sa.CheckConstraint(
            "cancellation_reason_code IS NULL OR "
            "length(btrim(cancellation_reason_code)) > 0",
            name="ck_appointments_cancellation_reason_not_blank",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name="ck_appointments_updated_after_created"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_appointments_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_appointments_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_appointments_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_location_id"],
            ["service_locations.id"],
            name="fk_appointments_service_location_id_service_locations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rescheduled_by_user_id"],
            ["users.id"],
            name="fk_appointments_rescheduled_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"],
            ["users.id"],
            name="fk_appointments_cancelled_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_appointments_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_appointments_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
        sa.UniqueConstraint(
            "company_id",
            "appointment_number",
            name="uq_appointments_company_number",
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "id",
            name="uq_appointments_company_branch_id",
        ),
    )
    op.create_index(
        "ix_appointments_company_branch_window",
        "appointments",
        ["company_id", "branch_id", "arrival_window_start_at", "id"],
    )
    op.create_index(
        "ix_appointments_company_status_window",
        "appointments",
        ["company_id", "status", "arrival_window_start_at", "id"],
    )
    op.create_index("ix_appointments_customer_id", "appointments", ["customer_id"])
    op.create_index(
        "ix_appointments_service_location_id",
        "appointments",
        ["service_location_id"],
    )

    op.execute(
        """
        CREATE FUNCTION validate_appointment_customer_location() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM customers
                WHERE id = NEW.customer_id
                  AND company_id = NEW.company_id
            ) THEN
                RAISE EXCEPTION 'Appointment Customer must belong to the Company';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM service_locations
                WHERE id = NEW.service_location_id
                  AND customer_id = NEW.customer_id
            ) THEN
                RAISE EXCEPTION 'Appointment Service Location must belong to the Customer';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_appointments_customer_location
        BEFORE INSERT OR UPDATE OF company_id, customer_id, service_location_id
        ON appointments
        FOR EACH ROW EXECUTE FUNCTION validate_appointment_customer_location()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_appointment_customer_company() RETURNS trigger AS $$
        BEGIN
            IF NEW.company_id IS DISTINCT FROM OLD.company_id AND EXISTS (
                SELECT 1
                FROM appointments
                WHERE customer_id = OLD.id
                  AND company_id <> NEW.company_id
            ) THEN
                RAISE EXCEPTION
                    'Customer Company cannot change while referenced by an Appointment';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_customers_protect_appointment_company
        BEFORE UPDATE OF company_id ON customers
        FOR EACH ROW EXECUTE FUNCTION protect_appointment_customer_company()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_appointment_service_location_customer()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.customer_id IS DISTINCT FROM OLD.customer_id AND EXISTS (
                SELECT 1
                FROM appointments
                WHERE service_location_id = OLD.id
                  AND customer_id <> NEW.customer_id
            ) THEN
                RAISE EXCEPTION
                    'Service Location Customer cannot change while referenced by an Appointment';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_service_locations_protect_appointment_customer
        BEFORE UPDATE OF customer_id ON service_locations
        FOR EACH ROW
        EXECUTE FUNCTION protect_appointment_service_location_customer()
        """
    )

    op.create_table(
        "appointment_capacity_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reserved_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity_units", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_override", sa.Boolean(), nullable=False),
        sa.Column("override_reason_code", sa.String(length=80), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "overridden_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reserved_end_at > reserved_start_at",
            name="ck_appointment_capacity_reservations_window",
        ),
        sa.CheckConstraint(
            "capacity_units > 0",
            name="ck_appointment_capacity_reservations_capacity",
        ),
        sa.CheckConstraint(
            "(released_at IS NULL AND release_reason_code IS NULL) OR "
            "(released_at IS NOT NULL AND release_reason_code IS NOT NULL)",
            name="ck_appointment_capacity_reservations_release_state",
        ),
        sa.CheckConstraint(
            "release_reason_code IS NULL OR length(btrim(release_reason_code)) > 0",
            name="ck_appointment_capacity_reservations_release_reason_not_blank",
        ),
        sa.CheckConstraint(
            "(is_override = false AND override_reason_code IS NULL "
            "AND overridden_at IS NULL AND overridden_by_user_id IS NULL) OR "
            "(is_override = true AND override_reason_code IS NOT NULL "
            "AND overridden_at IS NOT NULL)",
            name="ck_appointment_capacity_reservations_override_state",
        ),
        sa.CheckConstraint(
            "override_reason_code IS NULL OR length(btrim(override_reason_code)) > 0",
            name="ck_appointment_capacity_reservations_override_reason_not_blank",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_appointment_capacity_reservations_updated_after_created",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_appointment_capacity_reservations_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_appointment_capacity_reservations_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_appointment_capacity_reservations_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["overridden_by_user_id"],
            ["users.id"],
            name="fk_capacity_reservations_overridden_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointment_capacity_reservations"),
        sa.UniqueConstraint(
            "appointment_id",
            name="uq_appointment_capacity_reservations_appointment_id",
        ),
    )
    op.create_index(
        "ix_appointment_capacity_reservations_active_window",
        "appointment_capacity_reservations",
        [
            "company_id",
            "branch_id",
            "reserved_start_at",
            "reserved_end_at",
            "id",
        ],
        postgresql_where=sa.text("released_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_appointment_capacity_reservations_active_window",
        table_name="appointment_capacity_reservations",
    )
    op.drop_table("appointment_capacity_reservations")
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_service_locations_protect_appointment_customer ON service_locations"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS protect_appointment_service_location_customer()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_customers_protect_appointment_company ON customers"
    )
    op.execute("DROP FUNCTION IF EXISTS protect_appointment_customer_company()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_appointments_customer_location ON appointments"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_appointment_customer_location()")
    op.drop_index("ix_appointments_service_location_id", table_name="appointments")
    op.drop_index("ix_appointments_customer_id", table_name="appointments")
    op.drop_index("ix_appointments_company_status_window", table_name="appointments")
    op.drop_index("ix_appointments_company_branch_window", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index(
        "ix_branch_scheduling_exceptions_calendar_date",
        table_name="branch_scheduling_exceptions",
    )
    op.drop_table("branch_scheduling_exceptions")
    op.drop_index(
        "ix_branch_scheduling_weekly_intervals_calendar_day",
        table_name="branch_scheduling_weekly_intervals",
    )
    op.drop_table("branch_scheduling_weekly_intervals")
    op.drop_index(
        "ix_branch_scheduling_calendars_company_branch",
        table_name="branch_scheduling_calendars",
    )
    op.drop_table("branch_scheduling_calendars")
    op.drop_table("appointment_number_sequences")
