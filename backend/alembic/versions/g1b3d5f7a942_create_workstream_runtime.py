"""create authoritative workstream runtime and events

Revision ID: g1b3d5f7a942
Revises: f0a2c4e6b831
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "g1b3d5f7a942"
down_revision = "f0a2c4e6b831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engineering_workstream_controls",
        sa.Column("requested_action", sa.String(16), nullable=True),
    )
    op.execute(
        "UPDATE engineering_workstream_controls SET requested_action = CASE desired_state WHEN 'paused' THEN 'pause' WHEN 'cancelled' THEN 'cancel' ELSE 'start' END"
    )
    op.alter_column(
        "engineering_workstream_controls", "requested_action", nullable=False
    )
    op.create_check_constraint("ck_workstream_controls_requested_action", "engineering_workstream_controls", "requested_action IN ('start','pause','resume','cancel')")
    op.create_table(
        "engineering_workstream_runtimes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("acknowledged_control_version", sa.Integer(), nullable=False),
        sa.Column("acknowledged_action", sa.String(16), nullable=False),
        sa.Column("runtime_state", sa.String(32), nullable=False),
        sa.Column("worker_health", sa.String(24), nullable=False),
        sa.Column("progress_percent", sa.Integer()),
        sa.Column("current_activity", sa.String(240)),
        sa.Column("reason_code", sa.String(100)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "acknowledgement_expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_workstream_runtime_worker",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "runtime_state IN ('queued','acknowledged','running','paused','waiting_for_owner','validating','deploying_preview','completed','failed','cancelled','recovering')",
            name="ck_workstream_runtime_state",
        ),
        sa.CheckConstraint(
            "version >= 1 AND acknowledged_control_version >= 1",
            name="ck_workstream_runtime_versions",
        ),
        sa.CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name="ck_workstream_runtime_progress",
        ),
        sa.UniqueConstraint(
            "company_id", "command_id", name="uq_workstream_runtime_command"
        ),
    )
    op.create_table(
        "engineering_workstream_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_version", sa.Integer(), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True)),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("runtime_state", sa.String(32)),
        sa.Column("reason_code", sa.String(100)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["command_id"], ["engineering_commands.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_workstream_event_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("engineering_workstream_events")
    op.drop_table("engineering_workstream_runtimes")
    op.drop_constraint("ck_workstream_controls_requested_action", "engineering_workstream_controls", type_="check")
    op.drop_column("engineering_workstream_controls", "requested_action")
