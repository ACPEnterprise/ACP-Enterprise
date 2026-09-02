"""operationalize asset import and policy

Revision ID: l8m6p94e1r7s
Revises: k7l5n83d0q6r
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "l8m6p94e1r7s"
down_revision: str = "k7l5n83d0q6r"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_asset_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_type", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("predecessor_policy_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("policy_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], name="fk_asset_policy_branch", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["predecessor_policy_id"], ["operational_asset_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("policy_type IN ('inspection','maintenance','out_of_service','warranty','sensitive_identifier','import')", name="ck_asset_policy_type"),
        sa.CheckConstraint("status IN ('draft','active','superseded','unconfigured')", name="ck_asset_policy_status"),
        sa.CheckConstraint("version >= 1", name="ck_asset_policy_version"),
        sa.UniqueConstraint("company_id", "branch_id", "policy_type", "version", name="uq_asset_policy_version"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_asset_policy_command"),
    )
    op.create_index("ix_asset_policy_current", "operational_asset_policies", ["company_id", "branch_id", "policy_type", "status"])
    op.create_table(
        "operational_asset_import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_identity", sa.String(160), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("normalized_evidence", sa.JSON(), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("candidate_asset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], name="fk_asset_import_branch", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("source_type IN ('customer_equipment','vehicle','tracked_tool','company_equipment')", name="ck_asset_import_source_type"),
        sa.CheckConstraint("classification IN ('exact_identity','strong_candidate','ambiguous','insufficient_evidence','conflict','new_asset_candidate','replacement_candidate')", name="ck_asset_import_classification"),
        sa.CheckConstraint("disposition IN ('pending_review','accepted','rejected','blocked')", name="ck_asset_import_disposition"),
        sa.UniqueConstraint("company_id", "source_system", "source_identity", name="uq_asset_import_source"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_asset_import_command"),
    )
    op.create_index("ix_asset_import_review", "operational_asset_import_rows", ["company_id", "branch_id", "classification", "disposition"])
    for table in ("operational_asset_policies", "operational_asset_import_rows"):
        op.execute(f"CREATE RULE {table}_no_update AS ON UPDATE TO {table} DO INSTEAD NOTHING")
        op.execute(f"CREATE RULE {table}_no_delete AS ON DELETE TO {table} DO INSTEAD NOTHING")


def downgrade() -> None:
    op.drop_index("ix_asset_import_review", table_name="operational_asset_import_rows")
    op.drop_table("operational_asset_import_rows")
    op.drop_index("ix_asset_policy_current", table_name="operational_asset_policies")
    op.drop_table("operational_asset_policies")
