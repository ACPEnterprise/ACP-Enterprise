"""Add provider authorization grant history.

Revision ID: mf2b4d6f8h0j
Revises: mf1a3c5e7g9i
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "mf2b4d6f8h0j"
down_revision: str | Sequence[str] | None = "mf1a3c5e7g9i"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "migration_factory_provider_authorizations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "company_id", uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_company_digest", sa.String(64), nullable=False),
        sa.Column("authorized_scopes", postgresql.JSONB(), nullable=False),
        sa.Column("token_reference", sa.String(191), nullable=False),
        sa.Column("authorization_digest", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_id", uuid),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["migration_factory_provider_authorizations.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "provider", "authorization_digest",
            name="uq_migration_provider_authorization",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_migration_factory_provider_authorizations_immutable "
        "BEFORE UPDATE OR DELETE ON migration_factory_provider_authorizations "
        "FOR EACH ROW EXECUTE FUNCTION reject_migration_factory_evidence_mutation()"
    )


def downgrade() -> None:
    op.drop_table("migration_factory_provider_authorizations")
