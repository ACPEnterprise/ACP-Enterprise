"""Align Mission Control notifications with owner-action truth.

Revision ID: m8c0e2f4b719
Revises: l7b9d1e3a608
"""

from collections.abc import Sequence

from alembic import op

revision: str = "m8c0e2f4b719"
down_revision: str | None = "l7b9d1e3a608"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_mission_notification_kind",
        "engineering_mission_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mission_notification_kind",
        "engineering_mission_notifications",
        "kind IN ('waiting_for_owner','completed','failed','recovering',"
        "'heartbeat_expired','worker_disconnected','deployment_completed',"
        "'deployment_failed','manual_recovery')",
    )
    op.execute(
        "UPDATE engineering_mission_notifications "
        "SET status = 'archived', archived_at = COALESCE(archived_at, created_at), "
        "version = version + 1 "
        "WHERE kind NOT IN ('waiting_for_owner','manual_recovery') "
        "AND status <> 'archived'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE engineering_mission_notifications SET kind = 'recovering' "
        "WHERE kind = 'manual_recovery'"
    )
    op.drop_constraint(
        "ck_mission_notification_kind",
        "engineering_mission_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mission_notification_kind",
        "engineering_mission_notifications",
        "kind IN ('waiting_for_owner','completed','failed','recovering',"
        "'heartbeat_expired','worker_disconnected','deployment_completed',"
        "'deployment_failed')",
    )
