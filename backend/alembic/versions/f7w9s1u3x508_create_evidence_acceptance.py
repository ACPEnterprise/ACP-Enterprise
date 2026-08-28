"""create economics evidence acceptance

Revision ID: f7w9s1u3x508
Revises: e6v8r0t2w497
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7w9s1u3x508"
down_revision: str | Sequence[str] | None = "e6v8r0t2w497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_eco_policy_gap_state", "economics_company_policy_gaps", type_="check"
    )
    op.execute(
        "UPDATE economics_company_policy_gaps SET state = 'open' WHERE state = 'unresolved'"
    )
    op.execute(
        "UPDATE economics_company_policy_gaps SET state = 'satisfied' WHERE state = 'resolved'"
    )
    op.create_check_constraint(
        "ck_eco_policy_gap_state",
        "economics_company_policy_gaps",
        "state IN ('open','satisfied','conflicting','superseded')",
    )
    op.create_table(
        "economics_evidence_acceptance_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contract_id", sa.String(200), nullable=False),
        sa.Column("contract_version", sa.String(80), nullable=False),
        sa.Column("family_key", sa.String(100), nullable=False),
        sa.Column("gap_key", sa.String(120), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("contract_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "contract_id", "contract_version", name="uq_eco_acceptance_contract_version"
        ),
    )
    op.create_table(
        "economics_policy_gap_closures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "gap_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("economics_company_policy_gaps.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("subject_id", sa.String(200), nullable=False),
        sa.Column("reconciliation_key", sa.String(240), nullable=False),
        sa.Column("contract_id", sa.String(200), nullable=False),
        sa.Column("contract_version", sa.String(80), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_digests", postgresql.JSONB(), nullable=False),
        sa.Column("authorities", postgresql.JSONB(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provisional", sa.Boolean(), nullable=False),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("supersedes_closure_id", sa.String(128)),
        sa.Column("closure_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('open','satisfied','conflicting','superseded')",
            name="ck_eco_gap_closure_state",
        ),
        sa.UniqueConstraint(
            "company_id", "closure_digest", name="uq_eco_gap_closure_digest"
        ),
    )
    op.create_index(
        "ix_eco_gap_closure_replay",
        "economics_policy_gap_closures",
        ["company_id", "gap_id", "effective_date", "as_of"],
    )
    op.create_table(
        "economics_evidence_acceptance_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grant_id", sa.String(200), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subject_id", sa.String(200), nullable=False),
        sa.Column("contract_id", sa.String(200), nullable=False),
        sa.Column("contract_version", sa.String(80), nullable=False),
        sa.Column("evidence_id", sa.String(240), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("authority", sa.String(160), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date()),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grant_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "grant_id", name="uq_eco_acceptance_grant_identity"
        ),
        sa.UniqueConstraint(
            "company_id", "grant_digest", name="uq_eco_acceptance_grant_digest"
        ),
    )
    op.create_index(
        "ix_eco_acceptance_grant_replay",
        "economics_evidence_acceptance_grants",
        ["company_id", "contract_id", "subject_id", "effective_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eco_acceptance_grant_replay",
        table_name="economics_evidence_acceptance_grants",
    )
    op.drop_table("economics_evidence_acceptance_grants")
    op.drop_index(
        "ix_eco_gap_closure_replay", table_name="economics_policy_gap_closures"
    )
    op.drop_table("economics_policy_gap_closures")
    op.drop_table("economics_evidence_acceptance_contracts")
    op.drop_constraint(
        "ck_eco_policy_gap_state", "economics_company_policy_gaps", type_="check"
    )
    op.execute(
        "UPDATE economics_company_policy_gaps SET state = 'unresolved' WHERE state IN ('open','conflicting','superseded')"
    )
    op.execute(
        "UPDATE economics_company_policy_gaps SET state = 'resolved' WHERE state = 'satisfied'"
    )
    op.create_check_constraint(
        "ck_eco_policy_gap_state",
        "economics_company_policy_gaps",
        "state IN ('unresolved','resolved')",
    )
