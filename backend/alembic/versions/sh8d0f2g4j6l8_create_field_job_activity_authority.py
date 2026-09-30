"""create field Job activity and continuation authority

Revision ID: sh8d0f2g4j6l8
Revises: rg7c9e1f3i5k7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "sh8d0f2g4j6l8"
down_revision: str | Sequence[str] | None = "rg7c9e1f3i5k7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
U = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "field_job_activity_events",
        sa.Column("id", U, primary_key=True),
        sa.Column("company_id", U, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", U, nullable=False),
        sa.Column("employee_id", U, sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_id", U, nullable=False),
        sa.Column("appointment_id", U, nullable=False),
        sa.Column("assignment_id", U, sa.ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("activity", sa.String(24)),
        sa.Column("job_version", sa.Integer(), nullable=False),
        sa.Column("appointment_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("recorded_by_user_id", U, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id", "job_id"], ["jobs.company_id", "jobs.branch_id", "jobs.id"], name="fk_field_job_activity_events_job", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "branch_id", "appointment_id"], ["appointments.company_id", "appointments.branch_id", "appointments.id"], name="fk_field_job_activity_events_appointment", ondelete="RESTRICT"),
        sa.CheckConstraint("action IN ('start','change','finish_visit')", name="ck_field_job_activity_events_action"),
        sa.CheckConstraint("activity IS NULL OR activity IN ('working','parts_run')", name="ck_field_job_activity_events_activity"),
        sa.CheckConstraint("(action IN ('start','change') AND activity IS NOT NULL) OR (action = 'finish_visit' AND activity IS NULL)", name="ck_field_job_activity_events_shape"),
        sa.CheckConstraint("evidence_digest ~ '^[0-9a-f]{64}$'", name="ck_field_job_activity_events_digest"),
        sa.UniqueConstraint("company_id", "employee_id", "idempotency_key", name="uq_field_job_activity_events_idempotency"),
    )
    op.create_index("ix_field_job_activity_events_visit", "field_job_activity_events", ["company_id", "employee_id", "appointment_id", "occurred_at", "id"])
    op.create_table(
        "field_job_continuations",
        sa.Column("id", U, primary_key=True),
        sa.Column("company_id", U, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", U, nullable=False),
        sa.Column("employee_id", U, sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_id", U, nullable=False),
        sa.Column("appointment_id", U, sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignment_id", U, sa.ForeignKey("dispatch_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("requested_return_date", sa.Date()),
        sa.Column("needs_scheduling", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("recorded_by_user_id", U, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id", "job_id"], ["jobs.company_id", "jobs.branch_id", "jobs.id"], name="fk_field_job_continuations_job", ondelete="RESTRICT"),
        sa.CheckConstraint("reason IN ('parts_material','additional_labor','return_visit','multi_day_planned','inspection_permit','customer_availability','other')", name="ck_field_job_continuations_reason"),
        sa.CheckConstraint("needs_scheduling OR requested_return_date IS NOT NULL", name="ck_field_job_continuations_return"),
        sa.UniqueConstraint("company_id", "employee_id", "idempotency_key", name="uq_field_job_continuations_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("field_job_continuations")
    op.drop_index("ix_field_job_activity_events_visit", table_name="field_job_activity_events")
    op.drop_table("field_job_activity_events")
