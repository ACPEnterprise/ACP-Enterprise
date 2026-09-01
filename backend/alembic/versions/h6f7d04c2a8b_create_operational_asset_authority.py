"""create operational asset authority

Revision ID: h6f7d04c2a8b
Revises: g5e4c93b0f6d, i5h3g51b8z4x
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h6f7d04c2a8b"
down_revision: tuple[str, str] = ("g5e4c93b0f6d", "i5h3g51b8z4x")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common(table: str) -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "operational_assets",
        *_common("operational_assets"),
        sa.Column("asset_number", sa.String(80), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("predecessor_asset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("identity_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_assets_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_asset_id"], ["operational_assets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "asset_class IN ('customer_equipment','vehicle','tool','equipment','other_supported_asset')",
            name="ck_assets_class",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('active','inactive','retired','replaced','disposed')",
            name="ck_assets_lifecycle",
        ),
        sa.CheckConstraint("version >= 1", name="ck_assets_version"),
        sa.UniqueConstraint(
            "company_id", "asset_number", name="uq_assets_company_number"
        ),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_assets_command"),
        sa.UniqueConstraint("company_id", "id", name="uq_assets_company_id"),
    )
    op.create_index(
        "ix_assets_search",
        "operational_assets",
        ["company_id", "branch_id", "asset_class", "lifecycle"],
    )
    op.create_table(
        "operational_asset_evidence",
        *_common("operational_asset_evidence"),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("source_reference", sa.String(240)),
        sa.Column("protected_document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_evidence_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "evidence_type IN ('manufacturer','model','serial_reference','vin','license_plate','provider_identity','powertrain','odometer','condition','installation','removal','replacement','job_service','warranty','inspection','maintenance','readiness','document','custody')",
            name="ck_asset_evidence_type",
        ),
        sa.CheckConstraint(
            "state IN ('recorded','verified','unverified','eligible','not_eligible','expired','conflicting_evidence','insufficient_evidence','scheduled','due','completed','canceled','deferred','pass','attention_required','fail','not_applicable','unable_to_verify')",
            name="ck_asset_evidence_state",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_evidence_command"
        ),
        sa.UniqueConstraint(
            "company_id", "asset_id", "evidence_digest", name="uq_asset_evidence_digest"
        ),
    )
    op.create_index(
        "ix_asset_evidence_history",
        "operational_asset_evidence",
        ["company_id", "asset_id", "occurred_at"],
    )
    op.create_table(
        "operational_asset_relationships",
        *_common("operational_asset_relationships"),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(40), nullable=False),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_relationship_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "relationship_type IN ('customer','service_location','job','employee_custody','vehicle_custody','branch_custody','inventory_location','dispatch_context')",
            name="ck_asset_relationship_type",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_asset_relationship_period",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_relationship_command"
        ),
    )
    op.create_index(
        "ix_asset_relationship_active",
        "operational_asset_relationships",
        ["company_id", "asset_id", "relationship_type", "valid_to"],
    )
    op.create_table(
        "operational_asset_lifecycle_evidence",
        *_common("operational_asset_lifecycle_evidence"),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prior_state", sa.String(20), nullable=False),
        sa.Column("resulting_state", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(1000)),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_lifecycle_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_lifecycle_command"
        ),
    )
    op.create_index(
        "ix_asset_lifecycle_history",
        "operational_asset_lifecycle_evidence",
        ["company_id", "asset_id", "created_at"],
    )
    for table in (
        "operational_asset_evidence",
        "operational_asset_relationships",
        "operational_asset_lifecycle_evidence",
    ):
        op.execute(
            f"CREATE RULE {table}_immutable_update AS ON UPDATE TO {table} DO INSTEAD NOTHING"
        )
        op.execute(
            f"CREATE RULE {table}_immutable_delete AS ON DELETE TO {table} DO INSTEAD NOTHING"
        )


def downgrade() -> None:
    for table in (
        "operational_asset_lifecycle_evidence",
        "operational_asset_relationships",
        "operational_asset_evidence",
    ):
        op.drop_table(table)
    op.drop_table("operational_assets")
