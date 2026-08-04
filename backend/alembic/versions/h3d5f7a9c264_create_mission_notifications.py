"""create Mission Control notifications

Revision ID: h3d5f7a9c264
Revises: g2c4e6a8b153
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h3d5f7a9c264"
down_revision = "g2c4e6a8b153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engineering_mission_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["event_id"], ["engineering_workstream_events.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "kind IN ('waiting_for_owner','completed','failed','recovering',"
            "'heartbeat_expired','worker_disconnected','deployment_completed',"
            "'deployment_failed')",
            name="ck_mission_notification_kind",
        ),
        sa.CheckConstraint(
            "severity IN ('information','warning','critical')",
            name="ck_mission_notification_severity",
        ),
        sa.CheckConstraint(
            "status IN ('unread','acknowledged')",
            name="ck_mission_notification_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_mission_notification_version"),
        sa.UniqueConstraint(
            "company_id", "event_id", name="uq_mission_notification_event"
        ),
    )
    op.create_index(
        "ix_mission_notification_company_status",
        "engineering_mission_notifications",
        ["company_id", "status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mission_notification_company_status",
        table_name="engineering_mission_notifications",
    )
    op.drop_table("engineering_mission_notifications")
