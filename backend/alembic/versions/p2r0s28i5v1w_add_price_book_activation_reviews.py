"""Add explicit candidate activation review approvals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p2r0s28i5v1w"
down_revision: str | None = "o1q9r27h4u0v"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_book_activation_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("price_version_id", sa.UUID(), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("price_approved_by_user_id", sa.UUID()),
        sa.Column("price_approved_at", sa.DateTime(timezone=True)),
        sa.Column("tax_approved_by_user_id", sa.UUID()),
        sa.Column("tax_approved_at", sa.DateTime(timezone=True)),
        sa.Column("effective_approved_by_user_id", sa.UUID()),
        sa.Column("effective_approved_at", sa.DateTime(timezone=True)),
        sa.Column("activation_authorized_by_user_id", sa.UUID()),
        sa.Column("activation_authorized_at", sa.DateTime(timezone=True)),
        sa.Column("rationale", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "draft_version >= 1", name="ck_price_book_activation_review_version"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "price_version_id"],
            ["price_book_price_versions.company_id", "price_book_price_versions.id"],
            name="fk_price_book_activation_review_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["price_approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tax_approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["effective_approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["activation_authorized_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "price_version_id",
            name="uq_price_book_activation_review_version",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_price_book_activation_review_company_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("price_book_activation_reviews")
