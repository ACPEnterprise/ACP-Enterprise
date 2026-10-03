"""Distinguish intentional unassignment from unreconciled capacity.

Revision ID: vl2n4p6r8t0v
Revises: uk1m3o5q7s9u
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "vl2n4p6r8t0v"
down_revision: str | Sequence[str] | None = "uk1m3o5q7s9u"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "capacity_state",
            sa.String(32),
            nullable=False,
            server_default="legacy_unreconciled",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE appointments AS appointment
            SET capacity_state = 'reserved'
            WHERE EXISTS (
                SELECT 1
                FROM appointment_capacity_reservations AS reservation
                WHERE reservation.company_id = appointment.company_id
                  AND reservation.branch_id = appointment.branch_id
                  AND reservation.appointment_id = appointment.id
                  AND reservation.released_at IS NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE appointments AS appointment
            SET capacity_state = 'intentionally_unassigned'
            WHERE capacity_state = 'legacy_unreconciled'
              AND EXISTS (
                SELECT 1
                FROM business_events AS event
                WHERE event.company_id = appointment.company_id
                  AND event.entity_id = appointment.id
                  AND event.event_type = 'appointment.created'
              )
              AND NOT EXISTS (
                SELECT 1
                FROM business_events AS event
                WHERE event.company_id = appointment.company_id
                  AND event.entity_id = appointment.id
                  AND event.event_type = 'appointment.migrated'
              )
            """
        )
    )
    op.create_check_constraint(
        "ck_appointments_capacity_state",
        "appointments",
        "capacity_state IN ('reserved', 'intentionally_unassigned', "
        "'legacy_unreconciled')",
    )
    op.alter_column("appointments", "capacity_state", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_appointments_capacity_state", "appointments", type_="check")
    op.drop_column("appointments", "capacity_state")
