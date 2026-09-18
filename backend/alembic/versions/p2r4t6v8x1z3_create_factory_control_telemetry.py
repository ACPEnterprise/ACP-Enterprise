"""create factory control telemetry

Revision ID: p2r4t6v8x1z3
Revises: p2r4t6v8x0z2
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p2r4t6v8x1z3"
down_revision = "p2r4t6v8x0z2"
branch_labels = None
depends_on = None

FACTORY_CONTROL_PERMISSION_ID = "83f50788-21b8-5ca5-8e5e-c1511643a132"
FACTORY_CONTROL_PERMISSION_CODE = "PLATFORM_FACTORY_CONTROL_READ"


def _persist_factory_control_permission() -> None:
    at = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            """
            INSERT INTO permissions
                (id, code, name, description, resource, action, status,
                 created_at, updated_at, retired_at)
            VALUES
                (CAST(:permission_id AS uuid), :permission_code,
                 'Platform Factory Control Read', NULL, 'factory_control', 'read',
                 'active', :at, :at, NULL)
            ON CONFLICT (code) DO UPDATE
            SET name = EXCLUDED.name, resource = EXCLUDED.resource,
                action = EXCLUDED.action, status = 'active',
                updated_at = EXCLUDED.updated_at, retired_at = NULL
            """
        ).bindparams(
            permission_id=FACTORY_CONTROL_PERMISSION_ID,
            permission_code=FACTORY_CONTROL_PERMISSION_CODE,
            at=at,
        )
    )


def upgrade() -> None:
    _persist_factory_control_permission()
    op.create_table(
        "factory_control_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lane_code", sa.String(80), nullable=False),
        sa.Column("milestone_code", sa.String(160)),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("lifecycle_state", sa.String(40)),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(event_type)) > 0", name="ck_factory_event_type"
        ),
        sa.CheckConstraint(
            "length(btrim(lane_code)) > 0", name="ck_factory_event_lane"
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0", name="ck_factory_event_idempotency"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("company_id", "id", name="uq_factory_events_company_id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_factory_events_idempotency"
        ),
    )
    op.create_index(
        "ix_factory_events_company_time",
        "factory_control_events",
        ["company_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_factory_events_lane_time",
        "factory_control_events",
        ["company_id", "lane_code", "occurred_at", "id"],
    )
    op.create_table(
        "factory_lane_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lane_code", sa.String(80), nullable=False),
        sa.Column("milestone_code", sa.String(160)),
        sa.Column("lifecycle_state", sa.String(40), nullable=False),
        sa.Column("queue_depth", sa.Integer(), nullable=False),
        sa.Column("active_since", sa.DateTime(timezone=True)),
        sa.Column("last_handoff_at", sa.DateTime(timezone=True)),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_factory_lane_state_version"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id", "lane_code", name="uq_factory_lane_state_lane"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_factory_lane_states_company_id"
        ),
    )
    op.create_index(
        "ix_factory_lane_state_company_status",
        "factory_lane_states",
        ["company_id", "lifecycle_state", "lane_code"],
    )
    op.create_table(
        "factory_control_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_key", sa.String(200), nullable=False),
        sa.Column("roadmap_digest", sa.String(64), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("lane_states", postgresql.JSONB(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_factory_snapshots_company_id"),
        sa.UniqueConstraint(
            "company_id", "snapshot_key", name="uq_factory_snapshots_key"
        ),
    )
    op.create_index(
        "ix_factory_snapshots_company_time",
        "factory_control_snapshots",
        ["company_id", "captured_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_factory_snapshots_company_time", table_name="factory_control_snapshots"
    )
    op.drop_table("factory_control_snapshots")
    op.drop_index(
        "ix_factory_lane_state_company_status", table_name="factory_lane_states"
    )
    op.drop_table("factory_lane_states")
    op.drop_index("ix_factory_events_lane_time", table_name="factory_control_events")
    op.drop_index("ix_factory_events_company_time", table_name="factory_control_events")
    op.drop_table("factory_control_events")
    op.execute(
        sa.text(
            """
            DELETE FROM permissions p
            WHERE p.id = CAST(:permission_id AS uuid)
              AND p.code = :permission_code
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id
              )
            """
        ).bindparams(
            permission_id=FACTORY_CONTROL_PERMISSION_ID,
            permission_code=FACTORY_CONTROL_PERMISSION_CODE,
        )
    )
