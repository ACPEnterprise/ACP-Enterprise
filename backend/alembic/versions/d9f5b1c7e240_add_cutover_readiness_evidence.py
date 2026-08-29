"""Add immutable Customer Migration cutover-readiness evidence.

Revision ID: d9f5b1c7e240
Revises: c8e4a0b6d139
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9f5b1c7e240"
down_revision: str | Sequence[str] | None = "c8e4a0b6d139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_migration_cutover_readiness_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "evaluated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("readiness_key", sa.String(64), nullable=False),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("completed_prerequisites", postgresql.JSONB(), nullable=False),
        sa.Column("missing_prerequisites", postgresql.JSONB(), nullable=False),
        sa.Column("blocking_conditions", postgresql.JSONB(), nullable=False),
        sa.Column("owner_disposition_counts", postgresql.JSONB(), nullable=False),
        sa.Column("reconciliation_counts", postgresql.JSONB(), nullable=False),
        sa.Column("confidence_basis_points", sa.Integer(), nullable=False),
        sa.Column("completeness_basis_points", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready_for_owner_review','not_ready')",
            name="ck_customer_cutover_readiness_status",
        ),
        sa.CheckConstraint(
            "confidence_basis_points BETWEEN 0 AND 10000 AND "
            "completeness_basis_points BETWEEN 0 AND 10000",
            name="ck_customer_cutover_readiness_scores",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_cutover_readiness_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "readiness_key",
            name="uq_customer_cutover_readiness_key",
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "evidence_digest",
            name="uq_customer_cutover_readiness_replay",
        ),
    )
    op.create_index(
        "ix_customer_cutover_readiness_latest",
        "customer_migration_cutover_readiness_evidence",
        ["company_id", "branch_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_cutover_readiness_latest",
        table_name="customer_migration_cutover_readiness_evidence",
    )
    op.drop_table("customer_migration_cutover_readiness_evidence")
