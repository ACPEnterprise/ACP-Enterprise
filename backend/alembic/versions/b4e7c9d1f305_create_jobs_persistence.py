"""create jobs persistence

Revision ID: b4e7c9d1f305
Revises: a9d4e6f2c781
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b4e7c9d1f305"
down_revision: str | None = "a9d4e6f2c781"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_number_sequences",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "last_value >= 0", name="ck_job_number_sequences_last_value"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_job_number_sequences_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("company_id", name="pk_job_number_sequences"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_number", sa.String(length=24), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("job_type_code", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("customer_reported_problem", sa.Text(), nullable=True),
        sa.Column("internal_description", sa.Text(), nullable=True),
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_reason_code", sa.String(length=80), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancellation_reason_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "job_number ~ '^JOB-[0-9]{6,}$'", name="ck_jobs_number_format"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'ready', 'in_progress', 'paused', "
            "'completed', 'cancelled')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint(
            "job_type_code IS NULL OR job_type_code ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_jobs_type_code_format",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent', 'emergency')",
            name="ck_jobs_priority",
        ),
        sa.CheckConstraint(
            "customer_reported_problem IS NULL OR "
            "length(btrim(customer_reported_problem)) > 0",
            name="ck_jobs_customer_problem_not_blank",
        ),
        sa.CheckConstraint(
            "internal_description IS NULL OR length(btrim(internal_description)) > 0",
            name="ck_jobs_internal_description_not_blank",
        ),
        sa.CheckConstraint(
            "concurrency_version >= 1", name="ck_jobs_concurrency_version"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL) OR "
            "(status IN ('ready', 'in_progress', 'paused', 'completed') "
            "AND activated_at IS NOT NULL) OR status = 'cancelled'",
            name="ck_jobs_activation_state",
        ),
        sa.CheckConstraint(
            "(status IN ('in_progress', 'paused', 'completed') "
            "AND started_at IS NOT NULL) OR "
            "(status IN ('draft', 'ready') AND started_at IS NULL) OR "
            "status = 'cancelled'",
            name="ck_jobs_start_state",
        ),
        sa.CheckConstraint(
            "(status = 'paused' AND paused_at IS NOT NULL "
            "AND pause_reason_code IS NOT NULL) OR "
            "(status <> 'paused' AND paused_at IS NULL "
            "AND pause_reason_code IS NULL)",
            name="ck_jobs_pause_state",
        ),
        sa.CheckConstraint(
            "pause_reason_code IS NULL OR length(btrim(pause_reason_code)) > 0",
            name="ck_jobs_pause_reason_not_blank",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL)",
            name="ck_jobs_completion_state",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancelled_by_user_id IS NOT NULL "
            "AND cancellation_reason_code IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL "
            "AND cancelled_by_user_id IS NULL "
            "AND cancellation_reason_code IS NULL)",
            name="ck_jobs_cancellation_state",
        ),
        sa.CheckConstraint(
            "cancellation_reason_code IS NULL OR "
            "length(btrim(cancellation_reason_code)) > 0",
            name="ck_jobs_cancellation_reason_not_blank",
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_jobs_updated_at"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_jobs_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_jobs_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_jobs_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_location_id"],
            ["service_locations.id"],
            name="fk_jobs_service_location_id_service_locations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"],
            ["users.id"],
            name="fk_jobs_completed_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"],
            ["users.id"],
            name="fk_jobs_cancelled_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_jobs_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_jobs_updated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("company_id", "job_number", name="uq_jobs_company_number"),
        sa.UniqueConstraint(
            "company_id", "branch_id", "id", name="uq_jobs_company_branch_id"
        ),
    )
    op.create_index(
        "ix_jobs_company_branch_status_created",
        "jobs",
        ["company_id", "branch_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_jobs_company_status_priority_created",
        "jobs",
        ["company_id", "status", "priority", "created_at", "id"],
    )
    op.create_index(
        "ix_jobs_company_customer_created",
        "jobs",
        ["company_id", "customer_id", "created_at", "id"],
    )
    op.create_index(
        "ix_jobs_company_service_location_created",
        "jobs",
        ["company_id", "service_location_id", "created_at", "id"],
    )
    op.create_index(
        "ix_jobs_company_completed",
        "jobs",
        ["company_id", "completed_at", "id"],
    )

    op.execute(
        """
        CREATE FUNCTION validate_job_customer_location() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM customers
                WHERE id = NEW.customer_id AND company_id = NEW.company_id
            ) THEN
                RAISE EXCEPTION 'Job Customer must belong to the Company';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM service_locations
                WHERE id = NEW.service_location_id
                  AND customer_id = NEW.customer_id
            ) THEN
                RAISE EXCEPTION 'Job Service Location must belong to the Customer';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_jobs_customer_location
        BEFORE INSERT OR UPDATE OF company_id, customer_id, service_location_id
        ON jobs
        FOR EACH ROW EXECUTE FUNCTION validate_job_customer_location()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_job_customer_company() RETURNS trigger AS $$
        BEGIN
            IF NEW.company_id IS DISTINCT FROM OLD.company_id AND EXISTS (
                SELECT 1 FROM jobs
                WHERE customer_id = OLD.id AND company_id <> NEW.company_id
            ) THEN
                RAISE EXCEPTION
                    'Customer Company cannot change while referenced by a Job';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_customers_protect_job_company
        BEFORE UPDATE OF company_id ON customers
        FOR EACH ROW EXECUTE FUNCTION protect_job_customer_company()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_job_service_location_customer() RETURNS trigger AS $$
        BEGIN
            IF NEW.customer_id IS DISTINCT FROM OLD.customer_id AND EXISTS (
                SELECT 1 FROM jobs
                WHERE service_location_id = OLD.id
                  AND customer_id <> NEW.customer_id
            ) THEN
                RAISE EXCEPTION
                    'Service Location Customer cannot change while referenced by a Job';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_service_locations_protect_job_customer
        BEFORE UPDATE OF customer_id ON service_locations
        FOR EACH ROW EXECUTE FUNCTION protect_job_service_location_customer()
        """
    )

    op.create_table(
        "job_appointment_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_sequence", sa.Integer(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "visit_sequence >= 1", name="ck_job_appointment_links_visit_sequence"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_job_appointment_links_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_job_appointment_links_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_job_appointment_links_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["linked_by_user_id"],
            ["users.id"],
            name="fk_job_appointment_links_linked_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_appointment_links"),
        sa.UniqueConstraint(
            "job_id",
            "appointment_id",
            name="uq_job_appointment_links_job_appointment",
        ),
        sa.UniqueConstraint(
            "job_id", "visit_sequence", name="uq_job_appointment_links_job_visit"
        ),
    )
    op.create_index(
        "ix_job_appointment_links_company_branch",
        "job_appointment_links",
        ["company_id", "branch_id", "job_id", "visit_sequence"],
    )
    op.create_index(
        "ix_job_appointment_links_appointment",
        "job_appointment_links",
        ["appointment_id", "job_id"],
    )

    op.execute(
        """
        CREATE FUNCTION validate_job_appointment_link() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM jobs j
                JOIN appointments a
                  ON a.id = NEW.appointment_id
                 AND a.company_id = NEW.company_id
                 AND a.branch_id = NEW.branch_id
                WHERE j.id = NEW.job_id
                  AND j.company_id = NEW.company_id
                  AND j.branch_id = NEW.branch_id
                  AND j.customer_id = a.customer_id
                  AND j.service_location_id = a.service_location_id
            ) THEN
                RAISE EXCEPTION
                    'Job Appointment must match Company, Branch, Customer, and Service Location';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_job_appointment_links_consistency
        BEFORE INSERT OR UPDATE OF company_id, branch_id, job_id, appointment_id
        ON job_appointment_links
        FOR EACH ROW EXECUTE FUNCTION validate_job_appointment_link()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_job_appointment_links_from_job_change()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM job_appointment_links l
                JOIN appointments a ON a.id = l.appointment_id
                WHERE l.job_id = OLD.id
                  AND (
                    l.company_id <> NEW.company_id
                    OR l.branch_id <> NEW.branch_id
                    OR a.customer_id <> NEW.customer_id
                    OR a.service_location_id <> NEW.service_location_id
                  )
            ) THEN
                RAISE EXCEPTION
                    'Job identity cannot invalidate an Appointment link';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_jobs_protect_appointment_links
        BEFORE UPDATE OF company_id, branch_id, customer_id, service_location_id
        ON jobs
        FOR EACH ROW EXECUTE FUNCTION protect_job_appointment_links_from_job_change()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_job_appointment_links_from_appointment_change()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM job_appointment_links l
                JOIN jobs j ON j.id = l.job_id
                WHERE l.appointment_id = OLD.id
                  AND (
                    l.company_id <> NEW.company_id
                    OR l.branch_id <> NEW.branch_id
                    OR j.customer_id <> NEW.customer_id
                    OR j.service_location_id <> NEW.service_location_id
                  )
            ) THEN
                RAISE EXCEPTION
                    'Appointment identity cannot invalidate a Job link';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_appointments_protect_job_links
        BEFORE UPDATE OF company_id, branch_id, customer_id, service_location_id
        ON appointments
        FOR EACH ROW
        EXECUTE FUNCTION protect_job_appointment_links_from_appointment_change()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_appointments_protect_job_links ON appointments"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "protect_job_appointment_links_from_appointment_change()"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_jobs_protect_appointment_links ON jobs")
    op.execute(
        "DROP FUNCTION IF EXISTS protect_job_appointment_links_from_job_change()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_job_appointment_links_consistency "
        "ON job_appointment_links"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_job_appointment_link()")
    op.drop_index(
        "ix_job_appointment_links_appointment", table_name="job_appointment_links"
    )
    op.drop_index(
        "ix_job_appointment_links_company_branch", table_name="job_appointment_links"
    )
    op.drop_table("job_appointment_links")
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_service_locations_protect_job_customer ON service_locations"
    )
    op.execute("DROP FUNCTION IF EXISTS protect_job_service_location_customer()")
    op.execute("DROP TRIGGER IF EXISTS trg_customers_protect_job_company ON customers")
    op.execute("DROP FUNCTION IF EXISTS protect_job_customer_company()")
    op.execute("DROP TRIGGER IF EXISTS trg_jobs_customer_location ON jobs")
    op.execute("DROP FUNCTION IF EXISTS validate_job_customer_location()")
    op.drop_index("ix_jobs_company_completed", table_name="jobs")
    op.drop_index("ix_jobs_company_service_location_created", table_name="jobs")
    op.drop_index("ix_jobs_company_customer_created", table_name="jobs")
    op.drop_index("ix_jobs_company_status_priority_created", table_name="jobs")
    op.drop_index("ix_jobs_company_branch_status_created", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("job_number_sequences")
