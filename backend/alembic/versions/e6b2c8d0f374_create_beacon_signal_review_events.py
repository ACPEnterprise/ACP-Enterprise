"""Create Beacon signal review events and catalog review permission.

Revision ID: e6b2c8d0f374
Revises: d5a1b7c9f263
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e6b2c8d0f374"
down_revision: str | Sequence[str] | None = "d5a1b7c9f263"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_ID = "8b115f20-b15a-4ab5-8f4e-2ecac6f1c103"
PERMISSION_CODE = "COMPANY_BEACON_REVIEW"


def upgrade() -> None:
    occurred_at = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            "INSERT INTO permissions "
            "(id, code, name, description, resource, action, status, "
            "created_at, updated_at, retired_at) "
            "VALUES (:id, :code, 'Company Beacon Review', NULL, "
            "'beacon', 'review', 'active', :occurred_at, :occurred_at, NULL) "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(
            id=UUID(PERMISSION_ID),
            code=PERMISSION_CODE,
            occurred_at=occurred_at,
        )
    )
    op.create_table(
        "beacon_signal_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_code", sa.String(160), nullable=False),
        sa.Column("signal_source", sa.String(40), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("actor_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snooze_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('acknowledge','review','snooze')",
            name="ck_beacon_review_events_action",
        ),
        sa.CheckConstraint(
            "(action = 'snooze' AND snooze_until IS NOT NULL "
            "AND snooze_until > action_at) OR "
            "(action <> 'snooze' AND snooze_until IS NULL)",
            name="ck_beacon_review_events_snooze",
        ),
        sa.CheckConstraint(
            "length(evidence_digest) = 64",
            name="ck_beacon_review_events_evidence_digest",
        ),
        sa.CheckConstraint(
            "length(btrim(rule_code)) BETWEEN 3 AND 160",
            name="ck_beacon_review_events_rule_code",
        ),
        sa.CheckConstraint(
            "signal_source IN ('scheduling','jobs','invoices')",
            name="ck_beacon_review_events_signal_source",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "actor_membership_id"],
            ["memberships.company_id", "memberships.id"],
            name="fk_beacon_review_events_actor_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_beacon_review_events_company_condition",
        "beacon_signal_review_events",
        ["company_id", "condition_key", "action_at", "id"],
    )
    op.create_index(
        "ix_beacon_review_events_company_created",
        "beacon_signal_review_events",
        ["company_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_beacon_review_events_company_created",
        table_name="beacon_signal_review_events",
    )
    op.drop_index(
        "ix_beacon_review_events_company_condition",
        table_name="beacon_signal_review_events",
    )
    op.drop_table("beacon_signal_review_events")
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE id = CAST(:id AS uuid) AND code = :code"
        ).bindparams(id=PERMISSION_ID, code=PERMISSION_CODE)
    )
