"""Create authoritative Employee Job worked-time evidence.

Revision ID: b2d4f6h8j0m3
Revises: a1c3e5g7i9k1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d4f6h8j0m3"
down_revision: str | Sequence[str] | None = "a1c3e5g7i9k1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timekeeping_job_clock_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("event_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("kind IN ('start','stop')", name="ck_job_clock_event_kind"),
        sa.CheckConstraint(
            "source IN ('employee_clock','authorized_manual')",
            name="ck_job_clock_event_source",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_job_clock_event_company"),
        sa.UniqueConstraint(
            "company_id",
            "recorded_by_user_id",
            "idempotency_key",
            name="uq_job_clock_event_idempotency",
        ),
    )
    op.create_index(
        "ix_job_clock_event_employee_time",
        "timekeeping_job_clock_events",
        ["company_id", "employee_id", "occurred_at"],
    )
    op.create_table(
        "timekeeping_job_interval_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stop_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("correction_state", sa.String(24), nullable=False),
        sa.Column("audit_lineage", postgresql.JSONB(), nullable=False),
        sa.Column("source_event_ids", postgresql.JSONB(), nullable=False),
        sa.Column("validity", sa.String(32), nullable=False),
        sa.Column("confidence", sa.String(24), nullable=False),
        sa.Column("correction_reason", sa.Text()),
        sa.Column("corrected_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["supersedes_revision_id"],
            ["timekeeping_job_interval_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["corrected_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("stop_at > start_at", name="ck_job_interval_time_order"),
        sa.CheckConstraint("duration_minutes > 0", name="ck_job_interval_duration"),
        sa.CheckConstraint("revision_number >= 1", name="ck_job_interval_revision"),
        sa.CheckConstraint(
            "source IN ('employee_clock','authorized_manual')",
            name="ck_job_interval_source",
        ),
        sa.CheckConstraint(
            "correction_state IN ('original','corrected','superseded')",
            name="ck_job_interval_correction_state",
        ),
        sa.CheckConstraint(
            "validity IN ('valid','correction_required')",
            name="ck_job_interval_validity",
        ),
        sa.CheckConstraint(
            "confidence IN ('authoritative','disputed')",
            name="ck_job_interval_confidence",
        ),
        sa.UniqueConstraint(
            "company_id",
            "interval_id",
            "revision_number",
            name="uq_job_interval_revision",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_job_interval_revision_company"
        ),
    )
    op.create_index(
        "ix_job_interval_job_time",
        "timekeeping_job_interval_revisions",
        ["company_id", "job_id", "start_at"],
    )
    op.create_index(
        "ix_job_interval_employee_time",
        "timekeeping_job_interval_revisions",
        ["company_id", "employee_id", "start_at"],
    )
    for table in (
        "timekeeping_job_clock_events",
        "timekeeping_job_interval_revisions",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_timekeeping_authority_mutation()"
        )


def downgrade() -> None:
    for table in (
        "timekeeping_job_interval_revisions",
        "timekeeping_job_clock_events",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_index(
        "ix_job_interval_employee_time", table_name="timekeeping_job_interval_revisions"
    )
    op.drop_index(
        "ix_job_interval_job_time", table_name="timekeeping_job_interval_revisions"
    )
    op.drop_table("timekeeping_job_interval_revisions")
    op.drop_index(
        "ix_job_clock_event_employee_time", table_name="timekeeping_job_clock_events"
    )
    op.drop_table("timekeeping_job_clock_events")
