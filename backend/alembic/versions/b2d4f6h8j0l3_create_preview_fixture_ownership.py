"""create Preview fixture ownership manifest

Revision ID: b2d4f6h8j0l3
Revises: n0p8r16g3t9u
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d4f6h8j0l3"
down_revision: str | None = "n0p8r16g3t9u"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_fixture_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fixture_key", sa.String(length=128), nullable=False),
        sa.Column("resource_key", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authority_type", sa.String(length=64), nullable=False),
        sa.Column("authority_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authority_digest", sa.String(length=64), nullable=False),
        sa.Column("lifecycle", sa.String(length=24), nullable=False),
        sa.Column("active_projection", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(authority_digest) = 64", name="ck_preview_fixture_resource_authority_digest"),
        sa.CheckConstraint("lifecycle IN ('active','released','audit_retained')", name="ck_preview_fixture_resource_lifecycle"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "fixture_key", "resource_key", name="uq_preview_fixture_resource_key"),
        sa.UniqueConstraint("company_id", "resource_type", "resource_id", name="uq_preview_fixture_resource_identity"),
    )


def downgrade() -> None:
    op.drop_table("preview_fixture_resources")
