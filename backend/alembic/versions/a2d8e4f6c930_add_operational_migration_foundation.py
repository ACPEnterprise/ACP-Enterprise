"""Add provider-neutral Job and Appointment migration foundation.

Revision ID: a2d8e4f6c930
Revises: f1c7d9e3b825
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a2d8e4f6c930"
down_revision: str | Sequence[str] | None = "f1c7d9e3b825"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_service_location_source_parent_scope",
        "service_location_source_identities",
        ["id", "company_id", "customer_id", "service_location_id"],
    )
    op.create_table(
        "operational_migration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('dry_run', 'import')",
            name="ck_operational_migration_runs_mode",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_operational_migration_runs_status",
        ),
        sa.CheckConstraint(
            "source_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count",
            name="ck_operational_migration_runs_reconcile",
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "operational_migration_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('job', 'appointment')",
            name="ck_operational_migration_progress_entity",
        ),
        sa.CheckConstraint(
            "processed_count = accepted_count + rejected_count + duplicate_count "
            "+ unresolved_count AND processed_count <= source_count",
            name="ck_operational_migration_progress_reconcile",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "entity_type", name="uq_operational_migration_progress_entity"
        ),
    )
    op.create_table(
        "operational_migration_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("record_index", sa.Integer(), nullable=False),
        sa.Column("source_id_sha256", sa.String(length=64), nullable=True),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('job', 'appointment')",
            name="ck_operational_migration_exceptions_entity",
        ),
        sa.CheckConstraint(
            "disposition IN ('rejected', 'duplicate', 'unresolved')",
            name="ck_operational_migration_exceptions_disposition",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "operational_migration_job_source_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_source_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "service_location_source_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_job_id", sa.String(length=191), nullable=False),
        sa.Column("source_job_number", sa.String(length=191), nullable=True),
        sa.Column("source_status", sa.String(length=40), nullable=False),
        sa.Column(
            "assigned_technician_source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "external_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_job_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_job_source_identity_customer_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "service_location_source_identity_id",
                "company_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "service_location_source_identities.id",
                "service_location_source_identities.company_id",
                "service_location_source_identities.customer_id",
                "service_location_source_identities.service_location_id",
            ],
            name="fk_job_source_identity_location_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_job_id",
            name="uq_job_source_identity",
        ),
        sa.UniqueConstraint(
            "company_id", "source_system", "job_id", name="uq_job_source_target"
        ),
        sa.UniqueConstraint(
            "id",
            "company_id",
            "branch_id",
            "job_id",
            "customer_id",
            "service_location_id",
            name="uq_job_source_parent_scope",
        ),
    )
    op.create_table(
        "operational_migration_appointment_source_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "job_source_identity_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("source_appointment_id", sa.String(length=191), nullable=False),
        sa.Column("source_status", sa.String(length=40), nullable=False),
        sa.Column(
            "assigned_technician_source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "external_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("first_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_appointment_source_identity_appointment_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "job_source_identity_id",
                "company_id",
                "branch_id",
                "job_id",
                "customer_id",
                "service_location_id",
            ],
            [
                "operational_migration_job_source_identities.id",
                "operational_migration_job_source_identities.company_id",
                "operational_migration_job_source_identities.branch_id",
                "operational_migration_job_source_identities.job_id",
                "operational_migration_job_source_identities.customer_id",
                "operational_migration_job_source_identities.service_location_id",
            ],
            name="fk_appointment_source_identity_job_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_run_id"], ["operational_migration_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_appointment_id",
            name="uq_appointment_source_identity",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "appointment_id",
            name="uq_appointment_source_target",
        ),
    )


def downgrade() -> None:
    op.drop_table("operational_migration_appointment_source_identities")
    op.drop_table("operational_migration_job_source_identities")
    op.drop_table("operational_migration_exceptions")
    op.drop_table("operational_migration_progress")
    op.drop_table("operational_migration_runs")
    op.drop_constraint(
        "uq_service_location_source_parent_scope",
        "service_location_source_identities",
        type_="unique",
    )
