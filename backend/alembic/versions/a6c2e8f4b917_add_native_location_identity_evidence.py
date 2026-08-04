"""Add migration-owned native Service Location identity evidence.

Revision ID: a6c2e8f4b917
Revises: d5a1b7c9f263
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a6c2e8f4b917"
down_revision: str | Sequence[str] | None = "d5a1b7c9f263"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_location_identity_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_source_identity_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("prior_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_entity_type", sa.String(30), nullable=False),
        sa.Column("observation_sha256", sa.String(64), nullable=False),
        sa.Column("source_location_id_sha256", sa.String(64), nullable=True),
        sa.Column("source_customer_id_sha256", sa.String(64), nullable=True),
        sa.Column("source_artifact_sha256", sa.String(64), nullable=False),
        sa.Column("source_record_sha256", sa.String(64), nullable=False),
        sa.Column("address_evidence_sha256", sa.String(64), nullable=True),
        sa.Column("classification", sa.String(80), nullable=False),
        sa.Column("readiness", sa.String(30), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("evidence_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_entity_type = 'service_location'",
            name="ck_location_identity_evidence_entity_type",
        ),
        sa.CheckConstraint(
            "evidence_version >= 1", name="ck_location_identity_version"
        ),
        sa.CheckConstraint(
            "readiness IN ('ready', 'reconciliation_required', 'exception')",
            name="ck_location_identity_evidence_readiness",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_location_identity_evidence_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["prior_evidence_id"],
            ["service_location_identity_evidence.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id"],
            ["customer_source_identities.id", "customer_source_identities.company_id"],
            name="fk_location_identity_evidence_customer_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "company_id", name="uq_location_identity_evidence_scope"
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_entity_type",
            "observation_sha256",
            "evidence_version",
            name="uq_location_identity_evidence_observation_version",
        ),
    )
    op.create_index(
        "ix_location_identity_evidence_review",
        "service_location_identity_evidence",
        ["company_id", "readiness", "classification"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_location_identity_evidence_review",
        table_name="service_location_identity_evidence",
    )
    op.drop_table("service_location_identity_evidence")
