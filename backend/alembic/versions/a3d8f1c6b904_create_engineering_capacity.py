"""create engineering capacity management

Revision ID: a3d8f1c6b904
Revises: e6b2c8d0f374
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3d8f1c6b904"
down_revision: str | None = "e6b2c8d0f374"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_engineering_commands_company_id_capacity",
        "engineering_commands",
        ["company_id", "id"],
    )
    op.create_table(
        "engineering_capacity_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("maximum_concurrent_workstreams", sa.Integer(), nullable=False),
        sa.Column("maximum_per_worker", sa.Integer(), nullable=False),
        sa.Column("reserved_capacity", sa.Integer(), nullable=False),
        sa.Column("auto_allocate_released_capacity", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "maximum_concurrent_workstreams >= 1",
            name="ck_capacity_policy_system_limit",
        ),
        sa.CheckConstraint(
            "maximum_per_worker >= 1", name="ck_capacity_policy_worker_limit"
        ),
        sa.CheckConstraint(
            "reserved_capacity >= 0", name="ck_capacity_policy_reserved_nonnegative"
        ),
        sa.CheckConstraint(
            "reserved_capacity <= maximum_concurrent_workstreams",
            name="ck_capacity_policy_reserved_within_limit",
        ),
        sa.CheckConstraint("version >= 1", name="ck_capacity_policy_version"),
        sa.UniqueConstraint("company_id", name="uq_capacity_policy_company"),
        sa.UniqueConstraint("company_id", "id", name="uq_capacity_policy_company_id"),
    )
    op.create_table(
        "engineering_capacity_machines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("machine_label", sa.String(120), nullable=False),
        sa.Column("expected_available_on", sa.Date()),
        sa.Column("enrollment_state", sa.String(20), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(btrim(machine_label)) > 0", name="ck_capacity_machine_label"
        ),
        sa.CheckConstraint(
            "enrollment_state IN ('unenrolled','enrolled','retired')",
            name="ck_capacity_machine_enrollment",
        ),
        sa.CheckConstraint(
            "(enrollment_state = 'enrolled' AND worker_id IS NOT NULL) OR enrollment_state <> 'enrolled'",
            name="ck_capacity_machine_enrolled_worker",
        ),
        sa.CheckConstraint("version >= 1", name="ck_capacity_machine_version"),
        sa.UniqueConstraint(
            "company_id", "machine_label", name="uq_capacity_machine_label"
        ),
        sa.UniqueConstraint(
            "company_id", "worker_id", name="uq_capacity_machine_worker"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_capacity_machine_company_id"),
    )
    op.create_table(
        "engineering_worker_capacities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("configured_limit", sa.Integer(), nullable=False),
        sa.Column("allocated_capacity", sa.Integer(), nullable=False),
        sa.Column("reserved_capacity", sa.Integer(), nullable=False),
        sa.Column("operational_state", sa.String(32), nullable=False),
        sa.Column("health_state", sa.String(20), nullable=False),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "machine_id"],
            [
                "engineering_capacity_machines.company_id",
                "engineering_capacity_machines.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("configured_limit >= 1", name="ck_worker_capacity_limit"),
        sa.CheckConstraint(
            "allocated_capacity >= 0", name="ck_worker_capacity_allocated"
        ),
        sa.CheckConstraint(
            "reserved_capacity >= 0", name="ck_worker_capacity_reserved"
        ),
        sa.CheckConstraint(
            "allocated_capacity + reserved_capacity <= configured_limit",
            name="ck_worker_capacity_within_limit",
        ),
        sa.CheckConstraint(
            "operational_state IN ('available','occupied','reserved','paused','offline','unhealthy','reconciliation_required')",
            name="ck_worker_capacity_operational_state",
        ),
        sa.CheckConstraint(
            "health_state IN ('healthy','degraded','unhealthy','unknown')",
            name="ck_worker_capacity_health_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_worker_capacity_version"),
        sa.UniqueConstraint(
            "company_id", "worker_id", name="uq_worker_capacity_worker"
        ),
        sa.UniqueConstraint(
            "company_id", "machine_id", name="uq_worker_capacity_machine"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_worker_capacity_company_id"),
    )
    op.create_table(
        "engineering_capacity_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_capacity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True)),
        sa.Column("owner_intent_reference", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("transition_source", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("release_reason", sa.String(200)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_capacity_id"],
            [
                "engineering_worker_capacities.company_id",
                "engineering_worker_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "command_id"],
            ["engineering_commands.company_id", "engineering_commands.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active','allocated','released','expired','reconciliation_required')",
            name="ck_capacity_reservation_status",
        ),
        sa.CheckConstraint(
            "transition_source IN ('owner','automatic','system')",
            name="ck_capacity_reservation_source",
        ),
        sa.CheckConstraint("version >= 1", name="ck_capacity_reservation_version"),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= reserved_at",
            name="ck_capacity_reservation_release_time",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_capacity_reservation_idempotency"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_capacity_reservation_company_id"
        ),
    )
    op.create_index(
        "uq_capacity_reservation_active_command",
        "engineering_capacity_reservations",
        ["company_id", "command_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('active','allocated','reconciliation_required')"
        ),
    )
    op.create_table(
        "engineering_capacity_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_capacity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("transition_source", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("release_reason", sa.String(200)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "worker_capacity_id"],
            [
                "engineering_worker_capacities.company_id",
                "engineering_worker_capacities.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reservation_id"],
            [
                "engineering_capacity_reservations.company_id",
                "engineering_capacity_reservations.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "command_id"],
            ["engineering_commands.company_id", "engineering_commands.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "execution_id"],
            ["engineering_executions.company_id", "engineering_executions.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active','released','reconciliation_required')",
            name="ck_capacity_allocation_status",
        ),
        sa.CheckConstraint(
            "transition_source IN ('owner','automatic','system')",
            name="ck_capacity_allocation_source",
        ),
        sa.CheckConstraint("version >= 1", name="ck_capacity_allocation_version"),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= allocated_at",
            name="ck_capacity_allocation_release_time",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_capacity_allocation_idempotency"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_capacity_allocation_company_id"
        ),
    )
    op.create_index(
        "uq_capacity_allocation_active_command",
        "engineering_capacity_allocations",
        ["company_id", "command_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active','reconciliation_required')"),
    )
    op.create_table(
        "engineering_capacity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True)),
        sa.Column("worker_capacity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("allocation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("transition_source", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["policy_id"], ["engineering_capacity_policies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["worker_capacity_id"],
            ["engineering_worker_capacities.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["engineering_capacity_reservations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["allocation_id"],
            ["engineering_capacity_allocations.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(btrim(event_type)) > 0", name="ck_capacity_event_type"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_capacity_event_idempotency"
        ),
    )
    op.create_index(
        "ix_capacity_events_company_occurred",
        "engineering_capacity_events",
        ["company_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_capacity_events_company_occurred", table_name="engineering_capacity_events"
    )
    op.drop_table("engineering_capacity_events")
    op.drop_index(
        "uq_capacity_allocation_active_command",
        table_name="engineering_capacity_allocations",
    )
    op.drop_table("engineering_capacity_allocations")
    op.drop_index(
        "uq_capacity_reservation_active_command",
        table_name="engineering_capacity_reservations",
    )
    op.drop_table("engineering_capacity_reservations")
    op.drop_table("engineering_worker_capacities")
    op.drop_table("engineering_capacity_machines")
    op.drop_table("engineering_capacity_policies")
    op.drop_constraint(
        "uq_engineering_commands_company_id_capacity",
        "engineering_commands",
        type_="unique",
    )
