"""Bind workstream runtime, event, and notification lineage.

Revision ID: y9x7w05r2p8n
Revises: x8w6v94q1o7m
"""

from collections.abc import Sequence

from alembic import op

revision: str = "y9x7w05r2p8n"
down_revision: str | Sequence[str] | None = "x8w6v94q1o7m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_workstream_controls_runtime_scope",
        "engineering_workstream_controls",
        ["company_id", "id", "command_id"],
    )
    op.drop_constraint(
        "fk_workstream_controls_command",
        "engineering_workstream_controls",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_workstream_controls_command_company",
        "engineering_workstream_controls",
        "engineering_commands",
        ["company_id", "command_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "engineering_workstream_runtimes_command_id_fkey",
        "engineering_workstream_runtimes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_workstream_runtime_control_scope",
        "engineering_workstream_runtimes",
        "engineering_workstream_controls",
        ["company_id", "control_id", "command_id"],
        ["company_id", "id", "command_id"],
        ondelete="RESTRICT",
    )

    op.create_unique_constraint(
        "uq_workstream_events_notification_scope",
        "engineering_workstream_events",
        ["company_id", "id", "command_id"],
    )
    op.drop_constraint(
        "engineering_workstream_events_command_id_fkey",
        "engineering_workstream_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_workstream_events_control_scope",
        "engineering_workstream_events",
        "engineering_workstream_controls",
        ["company_id", "control_id", "command_id"],
        ["company_id", "id", "command_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_workstream_events_worker_company",
        "engineering_workstream_events",
        "engineering_workers",
        ["company_id", "worker_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "engineering_mission_notifications_event_id_fkey",
        "engineering_mission_notifications",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_mission_notifications_event_scope",
        "engineering_mission_notifications",
        "engineering_workstream_events",
        ["company_id", "event_id", "command_id"],
        ["company_id", "id", "command_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_mission_notifications_event_scope",
        "engineering_mission_notifications",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_mission_notifications_event_id_fkey",
        "engineering_mission_notifications",
        "engineering_workstream_events",
        ["event_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_workstream_events_worker_company",
        "engineering_workstream_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_workstream_events_control_scope",
        "engineering_workstream_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_workstream_events_command_id_fkey",
        "engineering_workstream_events",
        "engineering_commands",
        ["command_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_workstream_events_notification_scope",
        "engineering_workstream_events",
        type_="unique",
    )

    op.drop_constraint(
        "fk_workstream_runtime_control_scope",
        "engineering_workstream_runtimes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_workstream_runtimes_command_id_fkey",
        "engineering_workstream_runtimes",
        "engineering_commands",
        ["command_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_workstream_controls_command_company",
        "engineering_workstream_controls",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_workstream_controls_command",
        "engineering_workstream_controls",
        "engineering_commands",
        ["command_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_workstream_controls_runtime_scope",
        "engineering_workstream_controls",
        type_="unique",
    )
