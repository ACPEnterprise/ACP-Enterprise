"""create Workday Time authority

Revision ID: i0z2v4x6a831
Revises: h9y1u3w5z720
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "i0z2v4x6a831"
down_revision: str | Sequence[str] | None = "h9y1u3w5z720"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timekeeping_pay_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("processing_date", sa.Date(), nullable=False),
        sa.Column("payday", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("schedule_definition_id", sa.String(160), nullable=False),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_time_pay_period_dates"
        ),
        sa.CheckConstraint(
            "processing_date >= period_end AND payday >= processing_date",
            name="ck_time_pay_period_processing",
        ),
        sa.UniqueConstraint(
            "company_id", "period_start", "period_end", name="uq_time_pay_period"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_time_pay_period_company"),
    )
    op.create_table(
        "timekeeping_punch_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_device_reference", sa.String(200)),
        sa.Column("event_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "kind IN ('clock_in','clock_out','break_start','break_end')",
            name="ck_time_punch_kind",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_time_punch_company"),
    )
    op.create_index(
        "ix_time_punch_employee_occurred",
        "timekeeping_punch_events",
        ["company_id", "employee_id", "occurred_at"],
    )
    op.create_table(
        "timekeeping_entry_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "supersedes_revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("timekeeping_entry_revisions.id", ondelete="RESTRICT"),
        ),
        sa.Column("lineage_revision_ids", postgresql.JSONB(), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("provenance", sa.String(32), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("end_at", sa.DateTime(timezone=True)),
        sa.Column("approved_duration_minutes", sa.Integer()),
        sa.Column("punch_event_ids", postgresql.JSONB(), nullable=False),
        sa.Column("manual_reason", sa.Text()),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column(
            "source_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "responsible_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("correction_reason", sa.Text()),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "provenance IN ('employee_punch','authorized_manual_entry')",
            name="ck_time_entry_provenance",
        ),
        sa.CheckConstraint(
            "state IN ('recorded','submitted','approved','corrected')",
            name="ck_time_entry_state",
        ),
        sa.CheckConstraint("revision_number >= 1", name="ck_time_entry_revision"),
        sa.CheckConstraint(
            "(start_at IS NOT NULL AND end_at IS NOT NULL AND end_at > start_at) OR approved_duration_minutes IS NOT NULL",
            name="ck_time_entry_duration_shape",
        ),
        sa.CheckConstraint(
            "approved_duration_minutes IS NULL OR approved_duration_minutes >= 0",
            name="ck_time_entry_duration",
        ),
        sa.CheckConstraint(
            "(provenance = 'employee_punch' AND manual_reason IS NULL) OR (provenance = 'authorized_manual_entry' AND manual_reason IS NOT NULL)",
            name="ck_time_entry_manual_reason",
        ),
        sa.UniqueConstraint(
            "company_id", "entry_id", "revision_number", name="uq_time_entry_revision"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_time_entry_revision_company"),
    )
    op.create_index(
        "ix_time_entry_employee_date",
        "timekeeping_entry_revisions",
        ["company_id", "employee_id", "work_date"],
    )
    op.create_table(
        "timekeeping_payroll_input_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_identity", sa.String(128), nullable=False),
        sa.Column("snapshot_version", sa.String(80), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pay_period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_revision_ids", postgresql.JSONB(), nullable=False),
        sa.Column("total_approved_minutes", sa.Integer(), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "pay_period_id"],
            ["timekeeping_pay_periods.company_id", "timekeeping_pay_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "snapshot_digest", name="uq_time_payroll_snapshot_digest"
        ),
    )


def downgrade() -> None:
    op.drop_table("timekeeping_payroll_input_snapshots")
    op.drop_index(
        "ix_time_entry_employee_date", table_name="timekeeping_entry_revisions"
    )
    op.drop_table("timekeeping_entry_revisions")
    op.drop_index(
        "ix_time_punch_employee_occurred", table_name="timekeeping_punch_events"
    )
    op.drop_table("timekeeping_punch_events")
    op.drop_table("timekeeping_pay_periods")
