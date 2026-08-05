"""Add native Customer identity consolidation evidence.

Revision ID: c8e4a0b6d139
Revises: b7d3f9a5c028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8e4a0b6d139"
down_revision: str | Sequence[str] | None = "b7d3f9a5c028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_customer_source_identities_branch_scope",
        "customer_source_identities",
        ["id", "company_id", "branch_id", "customer_id"],
    )
    op.create_table(
        "customer_identity_consolidation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_source_identity_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "evaluated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_entity_type", sa.String(30), nullable=False),
        sa.Column("source_identity_key", sa.String(64), nullable=False),
        sa.Column("source_customer_id_sha256", sa.String(64), nullable=True),
        sa.Column("consolidation_contract_version", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(60), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "observation_count >= 1", name="ck_customer_identity_consolidation_count"
        ),
        sa.CheckConstraint(
            "outcome IN ('resolved','unresolved','missing_source_identifier',"
            "'duplicate_source_evidence','conflicting_source_evidence','ambiguous_target',"
            "'existing_binding_conflict','company_branch_scope_conflict',"
            "'multiple_native_identities_one_customer')",
            name="ck_customer_identity_consolidation_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'resolved') = (customer_source_identity_id IS NOT NULL)",
            name="ck_customer_identity_consolidation_resolved_target",
        ),
        sa.CheckConstraint(
            "(customer_source_identity_id IS NULL) = (customer_id IS NULL)",
            name="ck_customer_identity_consolidation_target_pair",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_customer_identity_consolidation_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_source_identity_id", "company_id", "branch_id", "customer_id"],
            [
                "customer_source_identities.id",
                "customer_source_identities.company_id",
                "customer_source_identities.branch_id",
                "customer_source_identities.customer_id",
            ],
            name="fk_customer_identity_consolidation_target_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "source_system",
            "source_identity_key",
            "evidence_digest",
            name="uq_customer_identity_consolidation_replay",
        ),
    )
    op.create_index(
        "ix_customer_identity_consolidation_review",
        "customer_identity_consolidation_evidence",
        ["company_id", "branch_id", "outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_identity_consolidation_review",
        table_name="customer_identity_consolidation_evidence",
    )
    op.drop_table("customer_identity_consolidation_evidence")
    op.drop_constraint(
        "uq_customer_source_identities_branch_scope",
        "customer_source_identities",
        type_="unique",
    )
