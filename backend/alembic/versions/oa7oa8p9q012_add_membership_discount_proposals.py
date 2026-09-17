"""persist reviewable technician discount proposals.

This worker migration is intentionally based on the Estimate/Price Book lineage;
OM2E must reline it with the canonical integration head before deployment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "oa7oa8p9q012"
down_revision: Union[str, Sequence[str], None] = "v7l9h1d3e508"
branch_labels: Union[str, Sequence[str], None] = ("oa007_oa008_worker",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("pricing_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.alter_column("invoices", "pricing_evidence", server_default=None)
    op.create_table(
        "estimate_technician_discount_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("estimate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discount_type", sa.String(length=20), nullable=False),
        sa.Column("requested_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("amount_before", sa.Numeric(18, 2), nullable=False),
        sa.Column("membership_discount_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("proposed_final_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("approved_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("approved_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("applied_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("discount_type IN ('fixed','percentage')", name="ck_estimate_discount_proposal_type"),
        sa.CheckConstraint("state IN ('PROPOSED','PENDING_MANAGER_APPROVAL','APPROVED','REJECTED','CANCELLED')", name="ck_estimate_discount_proposal_state"),
        sa.CheckConstraint("requested_value >= 0", name="ck_estimate_discount_proposal_value"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "estimate_id"], ["estimate_proposals.company_id", "estimate_proposals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "revision_id"], ["estimate_revisions.company_id", "estimate_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_estimate_discount_proposal_idempotency"),
    )
    op.create_index("ix_estimate_discount_proposals_review", "estimate_technician_discount_proposals", ["company_id", "estimate_id", "state"])


def downgrade() -> None:
    op.drop_column("invoices", "pricing_evidence")
    op.drop_index("ix_estimate_discount_proposals_review", table_name="estimate_technician_discount_proposals")
    op.drop_table("estimate_technician_discount_proposals")
