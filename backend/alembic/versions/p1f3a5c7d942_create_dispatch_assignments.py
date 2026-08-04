"""create workforce availability and dispatch assignments

Revision ID: p1f3a5c7d942
Revises: o0e2f4a6c931
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p1f3a5c7d942"
down_revision: str | None = "o0e2f4a6c931"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workforce_working_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("concurrency_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "profile_id"],
            [
                "workforce_capability_profiles.company_id",
                "workforce_capability_profiles.id",
            ],
            name="fk_workforce_availability_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_workforce_availability_branch",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "end_at > start_at", name="ck_workforce_availability_window"
        ),
        sa.CheckConstraint(
            "status IN ('available','unavailable','cancelled')",
            name="ck_workforce_availability_status",
        ),
        sa.CheckConstraint(
            "concurrency_version >= 1", name="ck_workforce_availability_version"
        ),
        sa.UniqueConstraint(
            "company_id",
            "profile_id",
            "branch_id",
            "start_at",
            "end_at",
            name="uq_workforce_availability_window",
        ),
    )
    op.create_index(
        "ix_workforce_availability_lookup",
        "workforce_working_availability",
        ["company_id", "branch_id", "start_at", "end_at", "status"],
    )
    op.create_table(
        "dispatch_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("primary_employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assignment_reason", sa.String(500), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_at", sa.DateTime(timezone=True)),
        sa.Column("release_reason", sa.String(500)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_dispatch_assignments_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "appointment_id"],
            ["appointments.company_id", "appointments.branch_id", "appointments.id"],
            name="fk_dispatch_assignments_appointment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "primary_employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_dispatch_assignments_primary_employee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_dispatch_assignments_job",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('proposed','assigned','acknowledged','released','replaced','cancelled','reconciliation_required')",
            name="ck_dispatch_assignments_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_dispatch_assignments_version"),
        sa.CheckConstraint(
            "window_end_at > window_start_at", name="ck_dispatch_assignments_window"
        ),
        sa.CheckConstraint(
            "length(btrim(assignment_reason)) > 0",
            name="ck_dispatch_assignments_reason",
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "appointment_id",
            name="uq_dispatch_assignments_appointment",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_dispatch_assignments_company_id"
        ),
    )
    op.create_index(
        "ix_dispatch_assignments_board",
        "dispatch_assignments",
        ["company_id", "branch_id", "window_start_at", "status"],
    )
    op.create_index(
        "ix_dispatch_assignments_primary_window",
        "dispatch_assignments",
        ["company_id", "primary_employee_id", "window_start_at", "window_end_at"],
        postgresql_where=sa.text(
            "status IN ('proposed','assigned','acknowledged','reconciliation_required')"
        ),
    )
    op.create_table(
        "dispatch_crew_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column("removal_reason", sa.String(500)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["removed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["dispatch_assignments.company_id", "dispatch_assignments.id"],
            name="fk_dispatch_crew_assignment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_dispatch_crew_employee",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active','removed')", name="ck_dispatch_crew_status"
        ),
        sa.CheckConstraint("version >= 1", name="ck_dispatch_crew_version"),
    )
    op.create_index(
        "uq_dispatch_crew_active",
        "dispatch_crew_members",
        ["company_id", "assignment_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_dispatch_crew_employee_active",
        "dispatch_crew_members",
        ["company_id", "employee_id"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "dispatch_assignment_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("prior_status", sa.String(32)),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("primary_employee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.String(240)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["dispatch_assignments.company_id", "dispatch_assignments.id"],
            name="fk_dispatch_history_assignment",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version >= 1", name="ck_dispatch_history_version"),
        sa.UniqueConstraint(
            "company_id",
            "assignment_id",
            "version",
            name="uq_dispatch_history_assignment_version",
        ),
    )
    op.create_index(
        "ix_dispatch_history_assignment",
        "dispatch_assignment_history",
        ["company_id", "assignment_id", "occurred_at"],
    )
    op.create_index(
        "uq_dispatch_history_idempotency",
        "dispatch_assignment_history",
        ["company_id", "evidence_reference"],
        unique=True,
        postgresql_where=sa.text("evidence_reference IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("dispatch_assignment_history")
    op.drop_table("dispatch_crew_members")
    op.drop_table("dispatch_assignments")
    op.drop_table("workforce_working_availability")
