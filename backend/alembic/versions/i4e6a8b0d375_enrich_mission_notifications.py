"""Enrich Mission Control notification lifecycle.

Revision ID: i4e6a8b0d375
Revises: h3d5f7a9c264
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i4e6a8b0d375"
down_revision: str | None = "h3d5f7a9c264"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_mission_notification_status",
        "engineering_mission_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mission_notification_status",
        "engineering_mission_notifications",
        "status IN ('unread','read','acknowledged','archived')",
    )
    op.add_column(
        "engineering_mission_notifications",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "engineering_mission_notifications",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE engineering_mission_notifications SET status = 'acknowledged' "
        "WHERE status IN ('read', 'archived')"
    )
    op.drop_column("engineering_mission_notifications", "archived_at")
    op.drop_column("engineering_mission_notifications", "read_at")
    op.drop_constraint(
        "ck_mission_notification_status",
        "engineering_mission_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mission_notification_status",
        "engineering_mission_notifications",
        "status IN ('unread','acknowledged')",
    )
