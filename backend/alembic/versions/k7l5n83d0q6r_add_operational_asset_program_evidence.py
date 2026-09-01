"""add operational asset program evidence

Revision ID: k7l5n83d0q6r
Revises: j6k4m72c9p5q
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "k7l5n83d0q6r"
down_revision: str = "j6k4m72c9p5q"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_asset_action_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_version", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_action_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "action_type IN ('equipment_install','equipment_remove','equipment_replace','warranty_evidence','warranty_review','service_link','vehicle_assignment','inspection','maintenance','out_of_service','custody_transfer','custody_return','document_binding')",
            name="ck_asset_action_type",
        ),
        sa.CheckConstraint("asset_version >= 1", name="ck_asset_action_version"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_action_command"
        ),
        sa.UniqueConstraint(
            "company_id",
            "asset_id",
            "evidence_digest",
            name="uq_asset_action_digest",
        ),
    )
    op.create_index(
        "ix_asset_action_history",
        "operational_asset_action_evidence",
        ["company_id", "asset_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_asset_action_queue",
        "operational_asset_action_evidence",
        ["company_id", "branch_id", "action_type", "occurred_at"],
    )
    op.execute(
        "CREATE RULE operational_asset_action_no_update AS ON UPDATE TO operational_asset_action_evidence DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE operational_asset_action_no_delete AS ON DELETE TO operational_asset_action_evidence DO INSTEAD NOTHING"
    )


def downgrade() -> None:
    op.drop_index("ix_asset_action_queue", table_name="operational_asset_action_evidence")
    op.drop_index("ix_asset_action_history", table_name="operational_asset_action_evidence")
    op.drop_table("operational_asset_action_evidence")
