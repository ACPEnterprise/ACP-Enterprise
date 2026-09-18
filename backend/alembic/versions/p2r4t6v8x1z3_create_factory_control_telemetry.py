"""create platform-global Factory Control authority and telemetry

Revision ID: p2r4t6v8x1z3
Revises: q3s5u7w9y1a3
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p2r4t6v8x1z3"
down_revision = "q3s5u7w9y1a3"
branch_labels = None
depends_on = None

PERMISSIONS = (
    (
        "83f50788-21b8-5ca5-8e5e-c1511643a132",
        "PLATFORM_FACTORY_CONTROL_READ",
        "Platform Factory Control Read",
        "read",
    ),
    (
        "1a77b4e9-23d5-53b7-a2a7-e1ad21d69f2d",
        "PLATFORM_FACTORY_CONTROL_INGEST",
        "Platform Factory Control Ingest",
        "ingest",
    ),
    (
        "5ce67842-05c5-52d2-b86c-b0e298ab868a",
        "PLATFORM_FACTORY_CONTROL_SNAPSHOT",
        "Platform Factory Control Snapshot",
        "snapshot",
    ),
)


def _persist_permissions_fail_closed() -> None:
    at = datetime.now(timezone.utc)
    bind = op.get_bind()
    for permission_id, code, name, action in PERMISSIONS:
        existing = (
            bind.execute(
                sa.text(
                    """
                    SELECT id, name, resource, action, status, retired_at
                    FROM permissions WHERE code = :code
                    """
                ),
                {"code": code},
            )
            .mappings()
            .first()
        )
        if existing is not None:
            expected = (
                permission_id,
                name,
                "factory_control",
                action,
                "active",
                None,
            )
            actual = (
                str(existing["id"]),
                existing["name"],
                existing["resource"],
                existing["action"],
                existing["status"],
                existing["retired_at"],
            )
            if actual != expected:
                raise RuntimeError(
                    "unsafe Factory Control permission identity collision"
                )
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions
                    (id, code, name, description, resource, action, status,
                     created_at, updated_at, retired_at)
                VALUES
                    (CAST(:permission_id AS uuid), :code, :name, NULL,
                     'factory_control', :action, 'active', :at, :at, NULL)
                """
            ),
            {
                "permission_id": permission_id,
                "code": code,
                "name": name,
                "action": action,
                "at": at,
            },
        )


def upgrade() -> None:
    _persist_permissions_fail_closed()
    op.create_table(
        "platform_authority_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_type", sa.String(24), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("worker_identity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("authority_code", sa.String(40), nullable=False),
        sa.Column("permission_code", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("grant_reason", sa.Text(), nullable=False),
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "principal_type IN ('USER','WORKER_IDENTITY')",
            name="ck_platform_authority_principal_type",
        ),
        sa.CheckConstraint(
            "authority_code IN ('PLATFORM_OWNER','PLATFORM_ADMIN','FACTORY_CONTROLLER')",
            name="ck_platform_authority_code",
        ),
        sa.CheckConstraint(
            "permission_code IN ('PLATFORM_FACTORY_CONTROL_READ',"
            "'PLATFORM_FACTORY_CONTROL_INGEST',"
            "'PLATFORM_FACTORY_CONTROL_SNAPSHOT')",
            name="ck_platform_authority_permission",
        ),
        sa.CheckConstraint(
            "(principal_type = 'USER' AND user_id IS NOT NULL "
            "AND worker_identity_id IS NULL "
            "AND authority_code IN ('PLATFORM_OWNER','PLATFORM_ADMIN') "
            "AND permission_code = 'PLATFORM_FACTORY_CONTROL_READ') OR "
            "(principal_type = 'WORKER_IDENTITY' AND user_id IS NULL "
            "AND worker_identity_id IS NOT NULL "
            "AND authority_code = 'FACTORY_CONTROLLER' "
            "AND permission_code IN ('PLATFORM_FACTORY_CONTROL_INGEST',"
            "'PLATFORM_FACTORY_CONTROL_SNAPSHOT'))",
            name="ck_platform_authority_principal_semantics",
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked')", name="ck_platform_authority_status"
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL "
            "AND revoked_by_user_id IS NULL AND revocation_reason IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL "
            "AND revoked_by_user_id IS NOT NULL "
            "AND length(btrim(revocation_reason)) > 0)",
            name="ck_platform_authority_revocation",
        ),
        sa.CheckConstraint("version >= 1", name="ck_platform_authority_version"),
        sa.CheckConstraint(
            "length(btrim(grant_reason)) > 0",
            name="ck_platform_authority_grant_reason",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["worker_identity_id"], ["worker_identities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "uq_platform_authority_active_user_permission",
        "platform_authority_assignments",
        ["user_id", "permission_code"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_platform_authority_active_worker_permission",
        "platform_authority_assignments",
        ["worker_identity_id", "permission_code"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'active' AND worker_identity_id IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_platform_authority_user_status",
        "platform_authority_assignments",
        ["user_id", "status", "permission_code"],
    )
    op.create_index(
        "ix_platform_authority_worker_status",
        "platform_authority_assignments",
        ["worker_identity_id", "status", "permission_code"],
    )

    op.create_table(
        "factory_control_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("lane_code", sa.String(80), nullable=False),
        sa.Column("milestone_code", sa.String(160)),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("lifecycle_state", sa.String(40)),
        sa.Column("queue_depth", sa.Integer(), nullable=False),
        sa.Column("machine", sa.String(120)),
        sa.Column("current_assignment", sa.String(200)),
        sa.Column("next_queued_item", sa.String(200)),
        sa.Column("controlling_enterprise", sa.String(20)),
        sa.Column("self_refill_health", sa.String(40)),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "controller_worker_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "length(request_digest) = 64", name="ck_factory_event_request_digest"
        ),
        sa.CheckConstraint("queue_depth >= 0", name="ck_factory_event_queue_depth"),
        sa.CheckConstraint(
            "controlling_enterprise IS NULL OR "
            "controlling_enterprise IN ('OM1E','OM2E','LaptopE')",
            name="ck_factory_event_controller",
        ),
        sa.CheckConstraint(
            "self_refill_health IS NULL OR self_refill_health IN "
            "('SELF_REFILL_HEALTHY','ELIGIBLE_IDLE','WAITING_INTEGRATION',"
            "'HUMAN_GATE','PROVIDER_GATE','DEPENDENCY_BLOCKED','RATE_LIMITED',"
            "'UNSAFE_STOP','UNKNOWN')",
            name="ck_factory_event_self_refill",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["controller_worker_identity_id"],
            ["worker_identities.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_factory_events_idempotency"),
    )
    op.create_index(
        "ix_factory_events_time", "factory_control_events", ["occurred_at", "id"]
    )
    op.create_index(
        "ix_factory_events_lane_time",
        "factory_control_events",
        ["lane_code", "occurred_at", "id"],
    )
    op.create_index(
        "ix_factory_events_tenant_time",
        "factory_control_events",
        ["tenant_company_id", "occurred_at", "id"],
    )
    op.create_table(
        "factory_lane_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lane_code", sa.String(80), nullable=False),
        sa.Column("milestone_code", sa.String(160)),
        sa.Column("lifecycle_state", sa.String(40), nullable=False),
        sa.Column("queue_depth", sa.Integer(), nullable=False),
        sa.Column("machine", sa.String(120)),
        sa.Column("current_assignment", sa.String(200)),
        sa.Column("next_queued_item", sa.String(200)),
        sa.Column("controlling_enterprise", sa.String(20)),
        sa.Column("self_refill_health", sa.String(40)),
        sa.Column("active_since", sa.DateTime(timezone=True)),
        sa.Column("eligible_idle_since", sa.DateTime(timezone=True)),
        sa.Column("last_handoff_at", sa.DateTime(timezone=True)),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_event_key", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_factory_lane_state_version"),
        sa.CheckConstraint("queue_depth >= 0", name="ck_factory_lane_queue_depth"),
        sa.CheckConstraint(
            "controlling_enterprise IS NULL OR "
            "controlling_enterprise IN ('OM1E','OM2E','LaptopE')",
            name="ck_factory_lane_controller",
        ),
        sa.CheckConstraint(
            "self_refill_health IS NULL OR self_refill_health IN "
            "('SELF_REFILL_HEALTHY','ELIGIBLE_IDLE','WAITING_INTEGRATION',"
            "'HUMAN_GATE','PROVIDER_GATE','DEPENDENCY_BLOCKED','RATE_LIMITED',"
            "'UNSAFE_STOP','UNKNOWN')",
            name="ck_factory_lane_self_refill",
        ),
        sa.ForeignKeyConstraint(
            ["last_event_id"], ["factory_control_events.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("lane_code", name="uq_factory_lane_state_lane"),
    )
    op.create_index(
        "ix_factory_lane_state_status",
        "factory_lane_states",
        ["lifecycle_state", "lane_code"],
    )
    op.create_table(
        "factory_control_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("snapshot_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("roadmap_digest", sa.String(64), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("lane_states", postgresql.JSONB(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_worker_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(request_digest) = 64", name="ck_factory_snapshot_request_digest"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_worker_identity_id"],
            ["worker_identities.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("snapshot_key", name="uq_factory_snapshots_key"),
    )
    op.create_index(
        "ix_factory_snapshots_time",
        "factory_control_snapshots",
        ["captured_at", "id"],
    )
    op.create_index(
        "ix_factory_snapshots_tenant_time",
        "factory_control_snapshots",
        ["tenant_company_id", "captured_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_factory_snapshots_tenant_time", table_name="factory_control_snapshots"
    )
    op.drop_index("ix_factory_snapshots_time", table_name="factory_control_snapshots")
    op.drop_table("factory_control_snapshots")
    op.drop_index("ix_factory_lane_state_status", table_name="factory_lane_states")
    op.drop_table("factory_lane_states")
    op.drop_index("ix_factory_events_tenant_time", table_name="factory_control_events")
    op.drop_index("ix_factory_events_lane_time", table_name="factory_control_events")
    op.drop_index("ix_factory_events_time", table_name="factory_control_events")
    op.drop_table("factory_control_events")
    op.drop_index(
        "ix_platform_authority_worker_status",
        table_name="platform_authority_assignments",
    )
    op.drop_index(
        "ix_platform_authority_user_status",
        table_name="platform_authority_assignments",
    )
    op.drop_index(
        "uq_platform_authority_active_worker_permission",
        table_name="platform_authority_assignments",
    )
    op.drop_index(
        "uq_platform_authority_active_user_permission",
        table_name="platform_authority_assignments",
    )
    # Any bearer token minted while a global grant existed must become stale
    # before downgrade removes the grant evidence.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET authorization_version = authorization_version + 1,
                updated_at = now()
            WHERE id IN (
                SELECT DISTINCT user_id
                FROM platform_authority_assignments
                WHERE user_id IS NOT NULL AND status = 'active'
            )
            """
        )
    )
    op.drop_table("platform_authority_assignments")
    for permission_id, code, name, action in reversed(PERMISSIONS):
        # Delete only the exact unassigned row introduced by this revision.
        # A changed identity fails closed and is left for governed review.
        op.execute(
            sa.text(
                """
                DELETE FROM permissions p
                WHERE p.id = CAST(:permission_id AS uuid)
                  AND p.code = :code
                  AND p.name = :name
                  AND p.resource = 'factory_control'
                  AND p.action = :action
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id
                  )
                """
            ).bindparams(
                permission_id=permission_id, code=code, name=name, action=action
            )
        )
