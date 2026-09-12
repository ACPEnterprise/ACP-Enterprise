"""create protected password reset delivery

Revision ID: f6h8j0l2n4p6
Revises: e5g7i9k1m3o5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6h8j0l2n4p6"
down_revision: str | Sequence[str] | None = "e5g7i9k1m3o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "protected_password_reset_delivery_envelopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "password_reset_token_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_id", sa.String(length=100), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','claimed','delivered','destroyed')",
            name="ck_password_reset_delivery_envelope_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_password_reset_delivery_envelope_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["password_reset_token_id"],
            ["password_reset_tokens.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "password_reset_token_id",
            name="uq_password_reset_delivery_envelope_token",
        ),
    )


def downgrade() -> None:
    op.drop_table("protected_password_reset_delivery_envelopes")
