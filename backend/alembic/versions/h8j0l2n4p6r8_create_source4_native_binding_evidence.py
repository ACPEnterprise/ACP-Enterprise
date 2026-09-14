"""create SOURCE.4 native successor binding evidence

Revision ID: h8j0l2n4p6r8
Revises: g7i9k1m3o5q7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h8j0l2n4p6r8"
down_revision = "g7i9k1m3o5q7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hcp_source4_native_binding_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(length=40), nullable=False),
        sa.Column("source4_source_id", sa.String(length=191), nullable=False),
        sa.Column("native_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_source_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source4_source_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_digest", sa.String(length=64), nullable=False),
        sa.Column("predecessor_source_digest", sa.String(length=64), nullable=False),
        sa.Column("binding_digest", sa.String(length=64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("domain IN ('customer','service_location','job','appointment')", name="ck_hcp_source4_binding_domain"),
        sa.ForeignKeyConstraint(["master_run_id", "company_id", "branch_id"], ["hcp_migration_master_runs.id", "hcp_migration_master_runs.company_id", "hcp_migration_master_runs.branch_id"], name="fk_hcp_source4_binding_master_scope", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "domain", "source4_source_id", name="uq_hcp_source4_binding_source"),
        sa.UniqueConstraint("company_id", "domain", "native_id", name="uq_hcp_source4_binding_target"),
        sa.UniqueConstraint("binding_digest", name="uq_hcp_source4_binding_digest"),
    )


def downgrade() -> None:
    op.drop_table("hcp_source4_native_binding_evidence")
