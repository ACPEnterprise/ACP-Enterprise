"""create worker identity credentials

Revision ID: c4e6a8b0d215
Revises: b2d4f6a8c013
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c4e6a8b0d215"
down_revision: str | None = "c3e5a7b9d124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("registered_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_worker_identities_name"),
        sa.CheckConstraint(
            "state IN ('registered','active','suspended','revoked')",
            name="ck_worker_identities_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_worker_identities_version"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["registered_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_worker_identities_registering_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "name", name="uq_worker_identities_company_name"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_worker_identities_company_id"
        ),
    )
    op.create_index(
        "ix_worker_identities_company_state",
        "worker_identities",
        ["company_id", "state", "id"],
    )
    op.create_table(
        "worker_identity_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("verifier", sa.String(512), nullable=False),
        sa.Column("verifier_algorithm", sa.String(50), nullable=False),
        sa.Column("public_key_id", sa.String(200), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending','active','revoked','expired')",
            name="ck_worker_credentials_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_worker_credentials_version"),
        sa.CheckConstraint(
            "length(btrim(verifier)) > 0 AND length(btrim(verifier_algorithm)) > 0 "
            "AND length(btrim(public_key_id)) > 0",
            name="ck_worker_credentials_public_metadata",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at", name="ck_worker_credentials_expiry"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "identity_id"],
            ["worker_identities.company_id", "worker_identities.id"],
            name="fk_worker_credentials_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "identity_id",
            "version",
            name="uq_worker_credentials_identity_version",
        ),
    )
    op.create_index(
        "uq_worker_credentials_active_identity",
        "worker_identity_credentials",
        ["company_id", "identity_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_index(
        "ix_worker_credentials_public_key",
        "worker_identity_credentials",
        ["company_id", "public_key_id"],
        unique=True,
    )
    op.create_index(
        "ix_worker_credentials_expiration",
        "worker_identity_credentials",
        ["company_id", "state", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_worker_credentials_expiration",
        table_name="worker_identity_credentials",
    )
    op.drop_index(
        "ix_worker_credentials_public_key",
        table_name="worker_identity_credentials",
    )
    op.drop_index(
        "uq_worker_credentials_active_identity",
        table_name="worker_identity_credentials",
    )
    op.drop_table("worker_identity_credentials")
    op.drop_index("ix_worker_identities_company_state", table_name="worker_identities")
    op.drop_table("worker_identities")
