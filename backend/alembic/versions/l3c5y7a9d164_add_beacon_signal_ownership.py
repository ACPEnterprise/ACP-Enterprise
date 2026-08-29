"""Add durable Beacon acknowledgement and ownership workflow.

Revision ID: l3c5y7a9d164
Revises: k2b4x6z8c053
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "l3c5y7a9d164"
down_revision: str | Sequence[str] | None = "k2b4x6z8c053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    ("b91268d3-212b-4d27-a67c-0d307f2c2101", "COMPANY_BEACON_OWN", "own"),
    ("cc95f47c-a99a-40db-b294-4434654ade02", "COMPANY_BEACON_ASSIGN", "assign"),
)


def upgrade() -> None:
    occurred_at = datetime.now(timezone.utc)
    for permission_id, code, action in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, name, description, resource, "
                "action, status, created_at, updated_at, retired_at) VALUES "
                "(:id, :code, :name, NULL, 'beacon', :action, 'active', "
                ":at, :at, NULL) ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                id=UUID(permission_id),
                code=code,
                name=code.replace("_", " ").title(),
                action=action,
                at=occurred_at,
            )
        )
    table = "beacon_signal_review_events"
    op.drop_constraint("ck_beacon_review_events_action", table, type_="check")
    op.create_check_constraint(
        "ck_beacon_review_events_action",
        table,
        "action IN ('acknowledge','review','snooze','claim','assign','transfer','release')",
    )
    for column in (
        sa.Column("definition_id", sa.String(160)),
        sa.Column("definition_version", sa.Integer()),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("workflow_request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("workflow_version", sa.Integer()),
        sa.Column("acknowledged_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("previous_owner_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("owned_since", sa.DateTime(timezone=True)),
    ):
        op.add_column(table, column)
    op.create_foreign_key(
        "fk_beacon_workflow_branch",
        table,
        "branches",
        ["company_id", "branch_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    for column, name in (
        ("actor_user_id", "actor"),
        ("acknowledged_by_user_id", "acknowledger"),
        ("previous_owner_user_id", "previous_owner"),
        ("owner_user_id", "owner"),
    ):
        op.create_foreign_key(
            f"fk_beacon_workflow_{name}_user",
            table,
            "users",
            [column],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_unique_constraint(
        "uq_beacon_review_events_workflow_version",
        table,
        ["company_id", "condition_key", "workflow_version"],
    )
    op.create_unique_constraint(
        "uq_beacon_review_events_workflow_request",
        table,
        ["company_id", "workflow_request_id"],
    )
    op.create_check_constraint(
        "ck_beacon_workflow_version_positive",
        table,
        "workflow_version IS NULL OR workflow_version > 0",
    )
    op.create_check_constraint(
        "ck_beacon_workflow_definition",
        table,
        "workflow_version IS NULL OR (definition_id IS NOT NULL AND "
        "definition_version > 0 AND actor_user_id IS NOT NULL AND "
        "workflow_request_id IS NOT NULL)",
    )


def downgrade() -> None:
    table = "beacon_signal_review_events"
    op.drop_constraint("ck_beacon_workflow_definition", table, type_="check")
    op.drop_constraint("ck_beacon_workflow_version_positive", table, type_="check")
    op.drop_constraint(
        "uq_beacon_review_events_workflow_request", table, type_="unique"
    )
    op.drop_constraint(
        "uq_beacon_review_events_workflow_version", table, type_="unique"
    )
    for name in ("owner", "previous_owner", "acknowledger", "actor"):
        op.drop_constraint(f"fk_beacon_workflow_{name}_user", table, type_="foreignkey")
    op.drop_constraint("fk_beacon_workflow_branch", table, type_="foreignkey")
    for column in (
        "owned_since",
        "owner_user_id",
        "previous_owner_user_id",
        "acknowledged_at",
        "acknowledged_by_user_id",
        "workflow_version",
        "workflow_request_id",
        "actor_user_id",
        "branch_id",
        "definition_version",
        "definition_id",
    ):
        op.drop_column(table, column)
    op.drop_constraint("ck_beacon_review_events_action", table, type_="check")
    op.create_check_constraint(
        "ck_beacon_review_events_action",
        table,
        "action IN ('acknowledge','review','snooze')",
    )
    for permission_id, code, _action in PERMISSIONS:
        op.execute(
            sa.text(
                "DELETE FROM permissions WHERE id = CAST(:id AS uuid) AND code = :code"
            ).bindparams(id=permission_id, code=code)
        )
