"""Add native Service Location reconciliation evidence.

Revision ID: b7d3f9a5c028
Revises: a6c2e8f4b917
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7d3f9a5c028"
down_revision: str | Sequence[str] | None = "a6c2e8f4b917"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_location_identity_evidence_branch_scope",
        "service_location_identity_evidence",
        ["id", "company_id", "branch_id"],
    )
    op.create_table(
        "service_location_reconciliation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "identity_evidence_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("service_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "evaluated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("matching_contract_version", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_count >= 0", name="ck_location_reconciliation_candidate_count"
        ),
        sa.CheckConstraint(
            "outcome IN ('matched','no_match','identity_not_ready','duplicate_native_identity',"
            "'ambiguous_address','address_review_required','parent_mismatch',"
            "'existing_binding_conflict','company_branch_scope_conflict')",
            name="ck_location_reconciliation_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'matched') = (service_location_id IS NOT NULL)",
            name="ck_location_reconciliation_matched_target",
        ),
        sa.CheckConstraint(
            "(service_location_id IS NULL) = (customer_id IS NULL)",
            name="ck_location_reconciliation_target_pair",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_location_reconciliation_branch_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["identity_evidence_id", "company_id", "branch_id"],
            [
                "service_location_identity_evidence.id",
                "service_location_identity_evidence.company_id",
                "service_location_identity_evidence.branch_id",
            ],
            name="fk_location_reconciliation_identity_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_location_id", "customer_id"],
            ["service_locations.id", "service_locations.customer_id"],
            name="fk_location_reconciliation_target_customer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "identity_evidence_id",
            "evidence_digest",
            name="uq_location_reconciliation_replay",
        ),
    )
    op.create_index(
        "ix_location_reconciliation_review",
        "service_location_reconciliation_evidence",
        ["company_id", "branch_id", "outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_location_reconciliation_review",
        table_name="service_location_reconciliation_evidence",
    )
    op.drop_table("service_location_reconciliation_evidence")
    op.drop_constraint(
        "uq_location_identity_evidence_branch_scope",
        "service_location_identity_evidence",
        type_="unique",
    )
