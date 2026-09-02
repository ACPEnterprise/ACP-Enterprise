"""Add non-activating Price Book review and adjustment proposals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "n0p8q16g3t9u"
down_revision: str | None = "m9n7q05f2s8t"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_book_review_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("configuration_version", sa.String(120), nullable=False),
        sa.Column("review_type", sa.String(40), nullable=False),
        sa.Column("selector", postgresql.JSONB(), nullable=False),
        sa.Column("service_codes", postgresql.JSONB(), nullable=False),
        sa.Column("exclusions", postgresql.JSONB(), nullable=False),
        sa.Column("candidate_set_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("decision_reason", sa.String(500)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("decided_by_user_id", sa.UUID()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_price_book_review_batches_version"),
        sa.CheckConstraint(
            "candidate_set_digest ~ '^[0-9a-f]{64}$'",
            name="ck_price_book_review_batches_digest",
        ),
        sa.CheckConstraint(
            "review_type IN ('commercial_content','candidate_prices','tax_classification','membership','source_conflict')",
            name="ck_price_book_review_batches_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','approved','returned','excluded')",
            name="ck_price_book_review_batches_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_review_batches_company_id"
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_price_book_review_batches_key"
        ),
    )
    op.create_index(
        "ix_price_book_review_batches_queue",
        "price_book_review_batches",
        ["company_id", "status", "review_type", "created_at"],
    )
    op.create_table(
        "price_book_adjustment_proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("source_price_book_version", sa.String(120), nullable=False),
        sa.Column("recommendation_identity", sa.String(160), nullable=False),
        sa.Column("economics_evidence_version", sa.String(160)),
        sa.Column("model_version", sa.String(160)),
        sa.Column("affected_service_codes", postgresql.JSONB(), nullable=False),
        sa.Column("owner_exclusions", postgresql.JSONB(), nullable=False),
        sa.Column("transformation_kind", sa.String(30), nullable=False),
        sa.Column("transformation", postgresql.JSONB(), nullable=False),
        sa.Column("impacts", postgresql.JSONB(), nullable=False),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposal_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("approved_by_user_id", sa.UUID()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version >= 1", name="ck_price_book_adjustment_proposals_version"
        ),
        sa.CheckConstraint(
            "proposal_digest ~ '^[0-9a-f]{64}$'",
            name="ck_price_book_adjustment_proposals_digest",
        ),
        sa.CheckConstraint(
            "status IN ('draft','approved','returned','rejected','superseded')",
            name="ck_price_book_adjustment_proposals_status",
        ),
        sa.CheckConstraint(
            "transformation_kind IN ('percentage','fixed_amount','markup_policy')",
            name="ck_price_book_adjustment_proposals_kind",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_adjustment_proposals_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "recommendation_identity",
            name="uq_price_book_adjustment_recommendation",
        ),
    )
    op.create_index(
        "ix_price_book_adjustment_proposals_queue",
        "price_book_adjustment_proposals",
        ["company_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_price_book_adjustment_proposals_queue",
        table_name="price_book_adjustment_proposals",
    )
    op.drop_table("price_book_adjustment_proposals")
    op.drop_index(
        "ix_price_book_review_batches_queue", table_name="price_book_review_batches"
    )
    op.drop_table("price_book_review_batches")
