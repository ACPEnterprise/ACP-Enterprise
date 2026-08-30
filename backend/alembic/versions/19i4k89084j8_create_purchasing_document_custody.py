"""create purchasing document custody

Revision ID: 19i4k89084j8
Revises: 18h3j78973i7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "19i4k89084j8"
down_revision: str | Sequence[str] | None = "18h3j78973i7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchasing_document_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("filename", sa.String(240), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("storage_reference", sa.String(500), nullable=False),
        sa.Column("source_reference", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('purchase_order','requisition','receipt','discrepancy','purchase_return')",
            name="ck_purchasing_document_entity_type",
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64", name="ck_purchasing_document_digest"
        ),
        sa.CheckConstraint(
            "status IN ('active','superseded')", name="ck_purchasing_document_status"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_purchasing_document_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_purchasing_document_key"
        ),
        sa.UniqueConstraint(
            "company_id",
            "entity_type",
            "entity_id",
            "content_digest",
            name="uq_purchasing_document_content",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_purchasing_document_company"),
    )
    op.create_index(
        "ix_purchasing_document_entity",
        "purchasing_document_evidence",
        ["company_id", "entity_type", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_purchasing_document_entity", table_name="purchasing_document_evidence"
    )
    op.drop_table("purchasing_document_evidence")
