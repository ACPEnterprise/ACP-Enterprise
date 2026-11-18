"""Add immutable provider certification evidence.

Revision ID: mf3c5e7g9i1k
Revises: mf2b4d6f8h0j
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "mf3c5e7g9i1k"
down_revision: str | Sequence[str] | None = "mf2b4d6f8h0j"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "migration_factory_provider_certifications",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "company_id", uuid,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("conformance", postgresql.JSONB(), nullable=False),
        sa.Column("domains", postgresql.JSONB(), nullable=False),
        sa.Column("transformation_version", sa.String(80), nullable=False),
        sa.Column("certificate_digest", sa.String(64), nullable=False),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "provider", "certificate_digest",
            name="uq_migration_provider_certificate",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_migration_factory_provider_certifications_immutable "
        "BEFORE UPDATE OR DELETE ON migration_factory_provider_certifications "
        "FOR EACH ROW EXECUTE FUNCTION reject_migration_factory_evidence_mutation()"
    )


def downgrade() -> None:
    op.drop_table("migration_factory_provider_certifications")
